# Methodology v0.2

WZRY and the temporal SQLite source are not force-joined. Repeated team pairs are insufficient linkage evidence.

Synthetic `draft_game_id` values are stable row IDs only.

Hero Flexibility Index is normalized role entropy over the five known roles. Unknown roles are retained in processed data but excluded from entropy probabilities.

Synergy/counter tables use shrinkage toward 0.5 with prior strength 20. They are descriptive associations, not causal effects.

Temporal Elo predictions use ratings immediately before each dated series; ratings update only after the observed result.
