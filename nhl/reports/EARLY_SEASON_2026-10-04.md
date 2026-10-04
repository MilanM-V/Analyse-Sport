# Mode découverte : picks avant 10 matchs — backtest

Config de prod (Équilibré, 1 pari / match) + joueurs à moins de 10 matchs cette saison, G/GP et A/GP mélangés avec la saison passée (k = 10, au moins 20 matchs la saison passée), mise Kelly × 0,5. Seuil d'EV choisi sur la validation ; contrôle affiché à part.

## Validation 2023-24

| EV min découverte | Picks découverte | Mise | Gain | ROI | EV vs Pinnacle | Gain attendu sans avantage | Gain total saison (vs sans le mode) |
|---|---|---|---|---|---|---|---|
| 8% | 101 | 80.0 U | -6.5 U | -8.2% | -5.4% | -2.3 U | +105.0 U (-5.0) |
| 12% | 67 | 56.0 U | -0.6 U | -1.0% | -4.1% | -1.0 U | +109.5 U (-0.5) |
| 15% | 50 | 42.5 U | +6.5 U | +15.2% | -2.3% | -0.4 U | +118.5 U (+8.5) |

Sans le mode : 448 paris, +110.0 U.

## Contrôle 2024-25

| EV min découverte | Picks découverte | Mise | Gain | ROI | EV vs Pinnacle | Gain attendu sans avantage | Gain total saison (vs sans le mode) |
|---|---|---|---|---|---|---|---|
| 8% | 59 | 40.5 U | -0.5 U | -1.1% | -4.6% | -1.8 U | +46.2 U (-0.5) |
| 12% | 46 | 32.0 U | -4.4 U | -13.7% | -5.2% | -1.6 U | +42.3 U (-4.4) |
| 15% | 34 | 24.0 U | -0.3 U | -1.1% | -5.8% | -1.3 U | +46.4 U (-0.3) |

Sans le mode : 236 paris, +46.7 U.

## Décision

Meilleur seuil en validation : EV ≥ 15% (+6.5 U).
