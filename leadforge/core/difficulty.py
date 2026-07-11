"""Recipe-driven difficulty resolution, shared across generation schemes.

Both the ``lead_scoring`` and ``lifecycle`` schemes turn ``config.difficulty``
(a tier name) into a :class:`~leadforge.core.models.DifficultyParams` by reading
the recipe's ``difficulty_profiles.yaml``.  Keeping that logic — recipe load,
profile lookup, required-key validation, param construction, and the
"no-profiles" policy — in one place stops the two schemes' resolvers from
drifting apart (they previously copy-pasted it and had already diverged).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from leadforge.core.models import DifficultyParams, GenerationConfig

# The knobs every difficulty profile must declare.  ``noise_scale`` /
# ``missing_rate`` / ``outlier_rate`` drive snapshot distortions today;
# ``signal_strength`` / ``conversion_rate_range`` / ``committee_friction`` are
# validated for a consistent cross-scheme contract and consumed by
# simulation-level scaling once that lands (issue #129).
_REQUIRED_PROFILE_KEYS = (
    "signal_strength",
    "noise_scale",
    "missing_rate",
    "outlier_rate",
    "conversion_rate_range",
    "committee_friction",
)


def resolve_difficulty_params(
    config: GenerationConfig,
) -> tuple[DifficultyParams | None, dict[str, Any] | None]:
    """Resolve ``DifficultyParams`` and the raw profile dict for *config*.

    Reads the recipe named by ``config.recipe_id`` and returns the
    :class:`DifficultyParams` for ``config.difficulty`` together with the raw
    profile mapping (so a caller can read scheme-specific extras such as
    ``category_latent_correlations``).

    Returns ``(None, None)`` when the recipe loads but declares no
    ``difficulty_profiles.yaml`` — i.e. "no difficulty modulation" rather than
    an error.  Propagates :class:`~leadforge.core.exceptions.InvalidRecipeError`
    when the recipe itself can't be loaded (an unknown ``recipe_id``) or when a
    profile *is* present but malformed (a required key is missing), so a real
    misconfiguration fails loudly instead of silently dropping distortions.
    """
    from leadforge.api.recipes import Recipe
    from leadforge.core.models import DifficultyParams
    from leadforge.recipes.registry import load_recipe

    # load_recipe raises InvalidRecipeError for an unknown recipe_id (propagated
    # deliberately — see docstring); a loadable recipe with no profiles file
    # yields {} here, which we treat as "no difficulty modulation".
    recipe = Recipe.from_dict(load_recipe(config.recipe_id))
    profiles = recipe.load_difficulty_profiles()
    if not profiles:
        return None, None

    profile = profiles.get(config.difficulty.value, {})
    missing = [k for k in _REQUIRED_PROFILE_KEYS if k not in profile]
    if missing:
        from leadforge.core.exceptions import InvalidRecipeError

        raise InvalidRecipeError(
            f"Difficulty profile '{config.difficulty.value}' is missing required keys: {missing}"
        )

    cr_range = profile["conversion_rate_range"]
    params = DifficultyParams(
        signal_strength=profile["signal_strength"],
        noise_scale=profile["noise_scale"],
        missing_rate=profile["missing_rate"],
        outlier_rate=profile["outlier_rate"],
        conversion_rate_lo=cr_range[0],
        conversion_rate_hi=cr_range[1],
        committee_friction=profile["committee_friction"],
    )
    return params, profile
