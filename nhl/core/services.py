import os
import requests
import logging
from datetime import datetime
from typing import Optional, Any, Dict, List, Callable
from functools import wraps

from telegram import Bot, ForceReply, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes, Application, CallbackQueryHandler,
                          MessageHandler, filters)
import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

# Re-export depuis shared.utils pour compatibilité ascendante
# (updater.py fait `from nhl.core.services import safe_get`)
from shared.utils import retry_request, safe_get, safe_post  # noqa: F401

PARIS_TZ = ZoneInfo("Europe/Paris")

logger = logging.getLogger("NHL.Services")

class TelegramNotifier:
    """Service to handle Telegram notifications via python-telegram-bot."""
    def __init__(self) -> None:
        """Initializes the TelegramNotifier with environment variables."""
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if self.token == "TELEGRAM_BOT_TOKEN" or not self.token:
            logger.warning("[TelegramNotifier] Token non valide ou manquant.")
            self.enabled = False
        else:
            self.enabled = True

        self.bot = Bot(token=self.token) if self.enabled else None

    def send_message(self, message: str) -> None:
        """
        Sends an HTML formatted message synchronously using the underlying bot.

        Args:
            message: The HTML message string to send.
        """
        if not self.enabled:
            return

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            safe_post(url, json=payload, timeout=10)
            logger.info("Alerte Telegram envoyée avec succès !")
        except Exception as e:
            logger.error(f"Exception lors de l'envoi Telegram : {e}")

    def send_pick_card(self, pick: Dict[str, Any], market: str) -> None:
        """Envoie à l'admin (chat privé) la fiche d'un pick avec les boutons Pris / Skip.

        Args:
            pick: pick enrichi (Joueur, Ref, CoteSeuil, Mise, IsHome, Match, Heure).
            market: 'but' ou 'ast'.
        """
        admin_id = os.getenv("TELEGRAM_ADMIN_ID")
        if not self.enabled or not admin_id or not pick.get("Ref"):
            return
        ref = pick["Ref"]
        payload = {
            "chat_id": admin_id,
            "text": pick_card_text(pick, market),
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": [[
                {"text": "✅ Pris", "callback_data": f"pick:take:{ref}"},
                {"text": "⏭️ Skip", "callback_data": f"pick:skip:{ref}"},
            ]]},
        }
        try:
            safe_post(f"https://api.telegram.org/bot{self.token}/sendMessage", json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Fiche privée non envoyée pour {pick.get('Joueur')} ({ref}) : {e}")

    def send_crash_alert(self, error: Exception, context: str = "Bot Principal") -> None:
        """
        Sends an emergency crash notification via Telegram.
        Uses raw requests (no retry decorator) to maximize delivery chance.

        Args:
            error: The exception that caused the crash.
            context: Description of where the crash occurred.
        """
        if not self.enabled:
            return

        import traceback
        tb = traceback.format_exc()
        # Tronquer le traceback à 500 chars pour ne pas dépasser la limite Telegram
        tb_short = tb[-500:] if len(tb) > 500 else tb

        message = (
            f"🚨 <b>CRASH — {context}</b>\n\n"
            f"<b>Erreur:</b> {type(error).__name__}: {error}\n\n"
            f"<pre>{tb_short}</pre>"
        )

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            # Utilise requests directement, pas safe_post, pour éviter les dépendances circulaires
            requests.post(url, json=payload, timeout=10)
            logger.info("🚨 Alerte crash envoyée sur Telegram.")
        except Exception as e:
            logger.error(f"Impossible d'envoyer l'alerte crash Telegram : {e}")

def pick_card_text(p: Dict[str, Any], market: str) -> str:
    """Texte HTML de la fiche privée d'un pick (contexte du match + cote seuil + mise)."""
    from nhl.core.formatter import format_match_time
    emoji, label = ("\U0001f525", "Buteur") if market == "but" else ("\U0001f170\ufe0f", "Passeur")
    lieu = "\U0001f3e0" if p.get("IsHome") else "\u2708\ufe0f"
    heure = f" · \U0001f552 {format_match_time(p['Heure'])}" if p.get("Heure") else ""
    seuil = f"{p['CoteSeuil']:.2f}" if p.get("CoteSeuil") else "?"
    return (f"{emoji} <b>{p['Joueur']}</b> {lieu} — {label}\n"
            f"{p.get('Match', '')}{heure}\n"
            f"à prendre si cote &gt; <b>{seuil}</b> · {p.get('Mise', '')}  <code>{p.get('Ref', '')}</code>")


def parse_odds_reply(text: str) -> Optional[tuple]:
    """'3.05', '3,05' ou '3.05 betclic' -> (3.05, 'betclic' | None) ; None si illisible."""
    parts = (text or "").strip().split()
    if not parts:
        return None
    try:
        cote = float(parts[0].replace(",", "."))
    except ValueError:
        return None
    if cote <= 1.01 or cote > 100:
        return None
    return cote, (parts[1].lower() if len(parts) > 1 else None)


def handle_pick_command(args: List[str], taken: bool) -> str:
    """Logique des commandes /pris et /skip (sans dépendance à Telegram, testable).

    Args:
        args: arguments de la commande : [ref, cote, book?] pour /pris, [ref] pour /skip.
        taken: True pour /pris, False pour /skip.

    Returns:
        Le texte de réponse à envoyer.
    """
    from nhl.config.settings import cfg
    from nhl.core.database import record_pick_decision
    if taken:
        if len(args) < 2:
            return "Usage : /pris <ref> <cote> [book]   ex. /pris B12 3.05 betclic"
        parsed = parse_odds_reply(args[1])
        if parsed is None:
            return f"❌ Cote invalide : {args[1]}"
        cote = parsed[0]
        book = args[2].lower() if len(args) > 2 else None
        r = record_pick_decision(args[0], cote, book)
    else:
        if not args:
            return "Usage : /skip <ref>   ex. /skip B12"
        r = record_pick_decision(args[0])
    if not r["ok"]:
        return f"❌ {r['error']}"
    if not taken:
        return f"⏭️ {r['joueur']} : pari non pris (exclu du ROI)."
    if r["under_threshold"]:
        return (f"⚠️ {r['joueur']} @{cote:.2f} est SOUS la cote seuil {r['cote_seuil']:.2f} : "
                "EV insuffisante, ne pas parier. Enregistré quand même — /skip pour annuler.")
    if not cfg.mode.paper_trading and r.get("mise"):
        from shared.portfolio import Portfolio
        market = "BUTEUR" if r["table"] == "picks" else "PASSEUR"
        Portfolio().log_bet("nhl", r["joueur"], market, cote, r["mise"], r["id"])
    return f"✅ {r['joueur']} pris @{cote:.2f}{' chez ' + book if book else ''} (seuil {r['cote_seuil'] or 0:.2f})."


def create_telegram_app(nhl_bot: Any) -> Optional[Application]:
    """
    Factory to create the interactive telegram application with handlers.

    Args:
        nhl_bot: The NhlBot instance to interact with.

    Returns:
        A configured telegram Application or None if token is missing.
    """
    token = os.getenv("TELEGRAM_TOKEN")
    if not token or token == "TELEGRAM_BOT_TOKEN":
        return None

    app = ApplicationBuilder().token(token).build()

    def admin_only(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            admin_id = os.getenv("TELEGRAM_ADMIN_ID")
            if not admin_id:
                if update.message:
                    await update.message.reply_text("❌ Sécurité: TELEGRAM_ADMIN_ID non configuré. Commandes bloquées.")
                return
            if str(update.effective_user.id) != admin_id:
                if update.message:
                    await update.message.reply_text("❌ Accès refusé : Vous n'êtes pas l'administrateur de ce bot.")
                return
            return await func(update, context)
        return wrapper

    @admin_only
    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /start command."""
        if update.message:
            await update.message.reply_text("🏒 NHL Bot V14 Actif ! Commandes:\n/status - État du bot\n/roi - Statistiques SQLite\n/portfolio - Solde\n/deposit - Ajouter des fonds\n/withdraw - Retirer des fonds\n/pause - Stopper les envois\n/resume - Reprendre\n/force - Lancer un scan\n\nChaque pick t'arrive ici en privé avec les boutons ✅ Pris / ⏭️ Skip.\n/pris B12 3.05 [book] - Corriger : pari pris à cette cote\n/skip B12 - Corriger : pari non pris")

    @admin_only
    async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /status command."""
        n_match_total = len(nhl_bot.matches_du_jour)
        n_match_traites = len(nhl_bot.matchs_traites)
        compo_en_attente = 0
        for match_id, data in nhl_bot.compos_en_memoire.items():
            time_str = data["match_info"]["time"]
            if time_str not in nhl_bot.vagues_envoyees:
                compo_en_attente += 1

        if update.message:
            await update.message.reply_text(f"📊 Status:\nMatchs détectés aujourd'hui: {n_match_total}\nMatchs avec compos traitées: {n_match_traites}\nCompos en attente de vague: {compo_en_attente}")

    @admin_only
    async def force_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /force command."""
        if update.message:
            await update.message.reply_text("⚡ Forçage du scan en cours (les logs vont s'afficher sur le serveur)...")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, nhl_bot.run_scan_cycle)
        if update.message:
            await update.message.reply_text("✅ Fin du scan forcé.")

    @admin_only
    async def roi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /roi command."""
        keyboard = [
            [
                InlineKeyboardButton("1 Jour", callback_data='roi_1'),
                InlineKeyboardButton("1 Semaine", callback_data='roi_7')
            ],
            [
                InlineKeyboardButton("1 Mois", callback_data='roi_30'),
                InlineKeyboardButton("All Time", callback_data='roi_all')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text("⏳ Sélectionnez la période pour le calcul du ROI :", reply_markup=reply_markup)

    @admin_only
    async def roi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        days = query.data.split('_')[1] # '1', '7', '30', 'all'
        label = f"{days} derniers jours" if days != "all" else "All Time"

        await query.edit_message_text(text=f"⏳ Calcul du ROI ({label})... Validation API en cours.")

        from nhl.core.updater import update_pending_picks
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, update_pending_picks)

        from nhl.core.database import get_roi_stats
        
        msg = f"💰 <b>ROI ({label})</b> :\n\n"
        msg += get_roi_stats("picks", "but", days) + "\n"
        msg += get_roi_stats("picks_assists", "assist", days) + "\n"
        
        # Ajout du ROI des combinés (Phase 4)
        try:
            msg += get_roi_stats("parlays", "combo", days)
        except Exception:
            pass
        
        await query.edit_message_text(text=msg, parse_mode="HTML")


    @admin_only
    async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /backup command."""
        if update.message:
            await update.message.reply_text("📦 Préparation de l'archive...")
        db_path = "./bot_database.db"
        if os.path.exists(db_path):
            with open(db_path, "rb") as db_file:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=db_file, filename="bot_database.db")
            if update.message:
                await update.message.reply_text("✅ Base de données sauvegardée avec succès.")
        elif update.message:
            await update.message.reply_text("❌ Base de données introuvable.")

    @admin_only
    async def resetdb_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /resetdb command."""
        if update.message:
            await update.message.reply_text("⚠️ Suppression de la base de données SQLite en cours...")
        from nhl.core.database import reset_db
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, reset_db)
        if update.message:
            await update.message.reply_text("✅ La base de données a été réinitialisée à 0.")

    @admin_only
    async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handler for /portfolio command."""
        import sys
        import os
        # Assurer l'accès à shared/ si non présent (bien que géré dans main_bot.py)
        if str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) not in sys.path:
            sys.path.append(str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            
        try:
            from shared.portfolio import Portfolio
            portfolio = Portfolio()
            balance = portfolio.get_balance()
            history = portfolio.get_history(limit=5)
            
            msg = "💼 <b>Portefeuille (Simulé)</b>\n"
            msg += f"Solde Actuel : <b>{balance:.2f} U</b>\n\n"
            msg += "Derniers paris :\n"
            if not history:
                msg += "<i>Aucun pari enregistré.</i>"
            else:
                for row in history:
                    statut = "⏳" if row['status'] == "PENDING" else ("✅" if row['status'] == "WIN" else "❌")
                    msg += f"{statut} {row['date_bet']} | {row['sport'].upper()} | {row['player_name']} (@{row['odds']}) - {row['stake_u']}U\n"
        except ImportError as e:
            msg = f"❌ Erreur de chargement du module Portfolio : {e}"
            
        if update.message:
            await update.message.reply_text(msg, parse_mode="HTML")

    @admin_only
    async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        nhl_bot.is_paused = True
        if update.message:
            await update.message.reply_text("⏸️ Le bot est en PAUSE. Le scan continuera en fond mais aucun pari ne sera envoyé.")

    @admin_only
    async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        nhl_bot.is_paused = False
        if update.message:
            await update.message.reply_text("▶️ Le bot a REPRIS. Les envois sont réactivés.")

    @admin_only
    async def deposit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /deposit <montant>")
            return
        try:
            amount = float(context.args[0])
            from shared.portfolio import Portfolio
            p = Portfolio()
            p.deposit(amount)
            await update.message.reply_text(f"✅ {amount} U ajoutés. Nouveau solde : {p.get_balance():.2f} U")
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur : {e}")

    @admin_only
    async def withdraw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /withdraw <montant>")
            return
        try:
            amount = float(context.args[0])
            from shared.portfolio import Portfolio
            p = Portfolio()
            p.withdraw(amount)
            await update.message.reply_text(f"✅ {amount} U retirés. Nouveau solde : {p.get_balance():.2f} U")
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur : {e}")

    @admin_only
    async def pris_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/pris <ref> <cote> [book] : pari pris à la cote réellement trouvée."""
        if update.message:
            await update.message.reply_text(handle_pick_command(context.args or [], taken=True))

    @admin_only
    async def skip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/skip <ref> : aucune cote FR au-dessus de la cote seuil, pari non pris."""
        if update.message:
            await update.message.reply_text(handle_pick_command(context.args or [], taken=False))

    def _is_admin(update: Update) -> bool:
        admin_id = os.getenv("TELEGRAM_ADMIN_ID")
        return bool(admin_id) and update.effective_user is not None and str(update.effective_user.id) == admin_id

    async def pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Boutons des fiches privées : pick:take:<ref> / pick:skip:<ref>."""
        query = update.callback_query
        if not _is_admin(update):
            await query.answer("Accès refusé", show_alert=True)
            return
        await query.answer()
        _, action, ref = query.data.split(":", 2)
        card = query.message.text_html if query.message else ""
        if action == "skip":
            reply = handle_pick_command([ref], taken=False)
            await query.edit_message_text(f"{card}\n\n{reply}", parse_mode="HTML")
            return
        context.user_data["await_odds"] = {"ref": ref, "chat_id": query.message.chat_id,
                                           "message_id": query.message.message_id, "card": card}
        await query.message.reply_text(f"À quelle cote as-tu pris {ref} ? (ex. 3.05 betclic)",
                                       reply_markup=ForceReply(selective=True))

    async def odds_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Réponse texte « 3.05 [book] » après un clic sur Pris."""
        pending = context.user_data.get("await_odds")
        if not pending or not _is_admin(update) or not update.message:
            return
        parsed = parse_odds_reply(update.message.text)
        if parsed is None:
            await update.message.reply_text("❌ Cote illisible. Réponds par exemple : 3.05 betclic")
            return
        cote, book = parsed
        reply = handle_pick_command([pending["ref"], str(cote)] + ([book] if book else []), taken=True)
        context.user_data.pop("await_odds", None)
        await update.message.reply_text(reply)
        try:
            await context.bot.edit_message_text(chat_id=pending["chat_id"], message_id=pending["message_id"],
                                                text=f"{pending['card']}\n\n{reply}", parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Fiche {pending['ref']} non mise à jour : {e}")

    app.add_handler(CallbackQueryHandler(pick_callback, pattern="^pick:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, odds_reply))
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("force", force_cmd))
    app.add_handler(CommandHandler("roi", roi_cmd))
    app.add_handler(CallbackQueryHandler(roi_callback, pattern='^roi_'))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("resetdb", resetdb_cmd))
    app.add_handler(CommandHandler("portfolio", portfolio_cmd))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("deposit", deposit_cmd))
    app.add_handler(CommandHandler("withdraw", withdraw_cmd))
    app.add_handler(CommandHandler("pris", pris_cmd))
    app.add_handler(CommandHandler("skip", skip_cmd))

    async def job_scan_cycle(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Fallback background job for scanning."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, nhl_bot.run_scan_cycle)

    async def job_clv_snapshot(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Snapshot des cotes de clôture (Winamax + Pinnacle no-vig) à T-5 d'un match."""
        from nhl.core.updater import log_closing_lines_for_match
        d = context.job.data
        try:
            await log_closing_lines_for_match(d["home"], d["away"], d["session_date"])
        except Exception as e:
            logger.error(f"[CLV] Échec snapshot {d['home']}-{d['away']} : {e}", exc_info=True)

    async def schedule_matches_dynamically(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Planifie, pour chaque match du jour, un scan à T-15 et un snapshot CLV à T-5."""
        logger.info("Planification dynamique des matchs du jour...")
        from nhl.core.scraper import get_scheduled_matches
        from nhl.core import loaders

        matches = get_scheduled_matches()
        now_utc = dt.datetime.now(dt.timezone.utc)
        session_date = nhl_bot.get_nhl_session_date()
        scheduled_scans = set()
        for m in matches:
            match_dt = nhl_bot.parse_match_datetime(m["time"])  # heure de Paris, naïve
            if not match_dt:
                continue
            start_utc = match_dt.replace(tzinfo=PARIS_TZ).astimezone(dt.timezone.utc)
            scan_utc = start_utc - dt.timedelta(minutes=15)
            if scan_utc > now_utc and scan_utc.strftime("%Y%m%d%H%M") not in scheduled_scans:
                context.job_queue.run_once(job_scan_cycle, when=scan_utc)
                scheduled_scans.add(scan_utc.strftime("%Y%m%d%H%M"))
                logger.info(f"Scan programmé à {match_dt - dt.timedelta(minutes=15):%H:%M} (T-15m) "
                            f"pour {m['home']} vs {m['away']}")
            clv_utc = start_utc - dt.timedelta(minutes=5)
            if clv_utc > now_utc:
                context.job_queue.run_once(job_clv_snapshot, when=clv_utc, data={
                    "home": loaders.clean_team_name(m["home"]), "away": loaders.clean_team_name(m["away"]),
                    "session_date": session_date})

    async def job_end_of_day(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Daily background job for cleanup."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, nhl_bot.end_of_day_cleanup)

    async def job_weekly_retrain(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Ré-entraînement hebdomadaire (gate intégré : n'écrase pas un meilleur modèle)."""
        import subprocess
        import sys
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script = os.path.join(repo_root, "nhl", "scripts", "train_models.py")
        logger.info("[Retrain] Ré-entraînement hebdomadaire des modèles...")
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: subprocess.run(
            [sys.executable, script, "--live"], cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace"))
        tail = (res.stdout or "")[-1500:]
        logger.info(f"[Retrain] code={res.returncode}\n{tail}")
        if res.returncode == 0:
            nhl_bot.engine.models = __import__("nhl.core.inference", fromlist=["load_models"]).load_models()
            gate = [ln.strip() for ln in (res.stdout or "").splitlines() if "[gate]" in ln]
            if gate:
                nhl_bot.telegram.send_message("🔁 <b>Retrain NHL</b>\n" + "\n".join(gate))
        else:
            nhl_bot.telegram.send_message(f"⚠️ <b>Retrain NHL en échec</b> (code {res.returncode})")

    async def job_drift_check(context: ContextTypes.DEFAULT_TYPE) -> None:
        """PSI des features servies (7 derniers jours) vs distribution d'entraînement."""
        from nhl.core.monitoring import drift_report
        loop = asyncio.get_running_loop()
        msg = await loop.run_in_executor(None, drift_report)
        if msg:
            nhl_bot.telegram.send_message(msg)

    # Planificateur : chaque jour à 13:00 UTC + une fois au démarrage
    target_time_planner = dt.time(hour=13, minute=0, tzinfo=dt.timezone.utc)
    app.job_queue.run_daily(schedule_matches_dynamically, time=target_time_planner)
    app.job_queue.run_once(schedule_matches_dynamically, when=10)

    # Filet de sécurité : scan toutes les 15 min (run_scan_cycle ignore lui-même
    # les heures inactives). Couvre les compos publiées après T-15 et les échecs API.
    app.job_queue.run_repeating(job_scan_cycle, interval=900, first=60)

    # EOD Cleanup at 5:00 UTC (morning)
    target_time_eod = dt.time(hour=5, minute=0, tzinfo=dt.timezone.utc)
    app.job_queue.run_daily(job_end_of_day, time=target_time_eod)

    # Contrôle de drift quotidien (6:00 UTC) et retrain hebdomadaire (lundi 6:30 UTC)
    app.job_queue.run_daily(job_drift_check, time=dt.time(hour=6, minute=0, tzinfo=dt.timezone.utc))
    app.job_queue.run_daily(job_weekly_retrain, time=dt.time(hour=6, minute=30, tzinfo=dt.timezone.utc),
                            days=(0,))

    # Backup Telegram at 5:15 UTC
    async def job_run_backup(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Lance le script de sauvegarde des bases de données."""
        logger.info("Lancement de la sauvegarde (Backup) à 5:15 UTC...")
        import subprocess
        import sys
        try:
            # Revenir à la racine du repo pour exécuter le script
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            backup_script = os.path.join(repo_root, "vps", "backup_manager.py")
            subprocess.run([sys.executable, backup_script], check=False)
        except Exception as e:
            logger.error(f"Échec de la sauvegarde : {e}")

    target_time_backup = dt.time(hour=5, minute=15, tzinfo=dt.timezone.utc)
    app.job_queue.run_daily(job_run_backup, time=target_time_backup)

    return app
