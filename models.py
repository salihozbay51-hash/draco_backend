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
GUMUS  = Dragon("gumus",  45,  500, 90)
ALTIN  = Dragon("altin",  65,  725, 90)
EFSANE = Dragon("efsane",105, 1170, 90)


DRAGONS = {d.code: d for d in [MINIK, CIRAK, BRONZ, GUMUS, ALTIN, EFSANE]}

