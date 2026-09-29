# Canonical Data Dictionary (target)

## series
`series_id`, `tournament_id`, `stage`, `start_time`, `team_a_id`, `team_b_id`, `score_a`, `score_b`, `winner_team_id`

## games
`game_id`, `series_id`, `game_number`, `start_time`, `blue_team_id`, `red_team_id`, `winner_team_id`, `duration_seconds`, `patch`

## draft_events
`draft_event_id`, `game_id`, `sequence`, `phase`, `action`, `team_id`, `hero_id`, `player_id`

## player_games
`game_id`, `player_id`, `team_id`, `hero_id`, `position`, `kills`, `deaths`, `assists`, `gold`, `damage`, `damage_taken`

Fields are populated only where source evidence supports them.
