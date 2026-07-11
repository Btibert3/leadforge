"""Tests for the shared recipe-driven difficulty resolver (LTV-Po.2b review).

This helper is called by both schemes' ``build_world`` paths; the tests pin the
contract that used to be copy-pasted (and had diverged) between them — in
particular the single "no difficulty profiles" policy.
"""

from __future__ import annotations

import pytest

from leadforge.core.difficulty import resolve_difficulty_params
from leadforge.core.exceptions import InvalidRecipeError
from leadforge.core.models import GenerationConfig


def test_resolves_params_and_profile_for_real_recipe() -> None:
    cfg = GenerationConfig(seed=1, recipe_id="b2b_saas_ltv_v1", difficulty="advanced")
    params, profile = resolve_difficulty_params(cfg)
    assert params is not None
    assert profile is not None
    # Active knobs come straight from difficulty_profiles.yaml (advanced tier).
    assert params.noise_scale == 0.55
    assert params.missing_rate == 0.18
    assert params.outlier_rate == 0.08


def test_tiers_differ() -> None:
    intro, _ = resolve_difficulty_params(
        GenerationConfig(seed=1, recipe_id="b2b_saas_ltv_v1", difficulty="intro")
    )
    advanced, _ = resolve_difficulty_params(
        GenerationConfig(seed=1, recipe_id="b2b_saas_ltv_v1", difficulty="advanced")
    )
    assert intro is not None
    assert advanced is not None
    assert intro.noise_scale < advanced.noise_scale


def test_returns_profile_extras_for_lead_scoring() -> None:
    # The lead-scoring intro profile carries category_latent_correlations; the
    # helper surfaces the raw profile dict so the scheme can read that extra.
    _, profile = resolve_difficulty_params(
        GenerationConfig(seed=1, recipe_id="b2b_saas_procurement_v1", difficulty="intro")
    )
    assert profile is not None
    assert "category_latent_correlations" in profile


def test_unknown_recipe_raises() -> None:
    # An unknown recipe_id is a real misconfiguration, not "no modulation" — it
    # propagates rather than silently resolving to no difficulty.
    with pytest.raises(InvalidRecipeError, match="not found"):
        resolve_difficulty_params(GenerationConfig(seed=1, recipe_id="does_not_exist_xyz"))


def test_no_profiles_file_returns_none_pair(monkeypatch) -> None:
    # Unified "no difficulty modulation" policy: a loadable recipe that declares
    # no difficulty_profiles.yaml resolves to (None, None) in BOTH schemes (this
    # is the fork the shared helper removed — lead-scoring used to raise here).
    from leadforge.api import recipes as recipes_mod
    from leadforge.recipes import registry as registry_mod

    class _NoProfilesRecipe:
        @staticmethod
        def from_dict(_raw):  # noqa: ANN001
            return _NoProfilesRecipe()

        def load_difficulty_profiles(self):
            return {}  # recipe.yaml present, difficulty_profiles.yaml absent

    monkeypatch.setattr(registry_mod, "load_recipe", lambda _rid: {"id": "stub"})
    monkeypatch.setattr(recipes_mod, "Recipe", _NoProfilesRecipe)

    params, profile = resolve_difficulty_params(GenerationConfig(seed=1, recipe_id="stub"))
    assert params is None
    assert profile is None


def test_malformed_profile_raises(monkeypatch) -> None:
    # A profile that is present but missing a required key must fail loudly
    # (not silently drop distortions).  resolve_difficulty_params imports Recipe
    # / load_recipe from their home modules at call time, so patching those
    # module attributes redirects the lookup.
    from leadforge.api import recipes as recipes_mod
    from leadforge.recipes import registry as registry_mod

    class _StubRecipe:
        @staticmethod
        def from_dict(_raw):  # noqa: ANN001
            return _StubRecipe()

        def load_difficulty_profiles(self):
            return {"intro": {"noise_scale": 0.1}}  # missing the other required keys

    monkeypatch.setattr(registry_mod, "load_recipe", lambda _rid: {"id": "stub"})
    monkeypatch.setattr(recipes_mod, "Recipe", _StubRecipe)

    cfg = GenerationConfig(seed=1, recipe_id="stub", difficulty="intro")
    with pytest.raises(InvalidRecipeError, match="missing required keys"):
        resolve_difficulty_params(cfg)
