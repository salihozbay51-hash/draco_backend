from dataclasses import dataclass

@dataclass(frozen=True)
class Dragon:
    code: str
    price_usdt: float
    eggs_per_day: int
    lifetime_days: int


MINIK  = Dragon("minik",   0,   2, 90)   # ücretsiz
CIRAK  = Dragon("cirak",  15,  170, 90)
BRONZ  = Dragon("bronz",  30,  335, 90)
GUMUS  = Dragon("gumus",  75,  800, 90)
ALTIN  = Dragon("altin",  110,  1300, 90)
EFSANE = Dragon("efsane", 180,  2200, 90)


DRAGONS = {d.code: d for d in [MINIK, CIRAK, BRONZ, GUMUS, ALTIN, EFSANE]}

