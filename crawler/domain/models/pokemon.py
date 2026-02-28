"""Modelos de domínio: Pokémon, stats e habilidades."""

from typing import Optional

from pydantic import BaseModel, Field


class BaseStats(BaseModel):
    """Atributos base (Base Stats) do Pokémon."""

    hp: int = Field(default=0, ge=0, le=255, description="Hit Points")
    attack: int = Field(default=0, ge=0, le=255, alias="Attack")
    defense: int = Field(default=0, ge=0, le=255, alias="Defense")
    sp_atk: int = Field(default=0, ge=0, le=255, alias="Sp. Atk")
    sp_def: int = Field(default=0, ge=0, le=255, alias="Sp. Def")
    speed: int = Field(default=0, ge=0, le=255, alias="Speed")

    class Config:
        populate_by_name = True


class AbilityInfo(BaseModel):
    """Uma habilidade, com flag opcional de Hidden Ability."""

    name: str
    is_hidden: bool = False


class GenderRatio(BaseModel):
    """Proporção de gênero em percentuais (0–100). No JSON: objeto com male e female."""

    male: Optional[float] = Field(default=None, ge=0, le=100, description="Percentual masculino")
    female: Optional[float] = Field(default=None, ge=0, le=100, description="Percentual feminino")


class Pokemon(BaseModel):
    """Entidade de domínio: Pokémon com dados da Bulbapedia."""

    name: str = ""
    national_dex_number: Optional[int] = None
    category: Optional[str] = None
    types: list[str] = Field(default_factory=list)
    base_stats: BaseStats = Field(default_factory=BaseStats)
    evolution_prev: Optional[str] = None
    evolution_next: Optional[str] = None
    abilities: list[AbilityInfo] = Field(default_factory=list)
    image_path: Optional[str] = None
    gender_ratio: Optional[GenderRatio] = None

    class Config:
        populate_by_name = True
