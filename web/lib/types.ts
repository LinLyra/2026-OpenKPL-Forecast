export type Group = "MASTER" | "ELITE";

export interface Envelope<T> {
  source_file: string[];
  source_sha256: string[];
  generated_at: string;
  generator: string;
  data: T;
}

export interface FreezeMeta {
  freeze_id: string;
  forecast_status: string;
  provisional_scope: string;
  created_at: string;
  information_cutoff: string;
  first_scheduled_match: string;
  model_version: string;
  data_version: string;
  git_tag: string;
  git_commit_tagged: string;
  git_commit_content: string;
  strength_file: string;
  strength_sha256: string;
  primary_forecast: string;
  primary_forecast_sha256: string;
  prediction_ledger: string;
  prediction_ledger_content_sha256: string;
  freeze_manifest_sha256: string;
  test_count: number;
  tests_passed: number;
  n_simulations: number;
}

export interface ForecastTeam {
  id: string;
  canonical_team_id: string;
  official_name: string;
  group: Group;
  seed: number | null;
  frozen_b5_rating: number;
  direct_knockout_probability: number;
  breakthrough_probability: number;
  stage1_elimination_probability: number;
  breakthrough_win_probability: number;
  knockout_probability: number;
  upper_semifinal_probability: number;
  upper_final_probability: number;
  drop_to_lower_bracket_probability: number;
  lower_final_probability: number;
  final_probability: number;
  championship_probability: number;
  mc_se_knockout: number;
  mc_se_final: number;
  mc_se_champion: number;
  n_simulations: number;
  sensitivity_only: {
    championship_probability_conservative: number;
    championship_probability_aggressive: number;
    championship_probability_bo7_sensitivity: number;
  };
}

export interface ForecastData {
  freeze: FreezeMeta;
  championship_probability_sum: number;
  label: string;
  teams: ForecastTeam[];
}

export interface RosterUsage {
  window: string;
  series_observed: number | null;
  mean_players_used_per_series: number | null;
  freq_series_at_least_6_players: number | null;
  freq_series_at_least_7_players: number | null;
  max_players_used_in_a_series: number | null;
  label: string;
  note: string;
}

export interface TeamStage1 {
  id: string;
  canonical_team_id: string;
  official_name: string;
  group: Group;
  seed: number | null;
  frozen_b5_rating: number;
  expected_series_wins: number;
  expected_game_diff: number;
  p_group_rank: number[];
  historical_roster_usage_descriptive: RosterUsage[];
}

export interface LedgerRow {
  ledger_key: string;
  stage: string;
  scheduled_date: string;
  format: string;
  team_a: string;
  team_a_id: string;
  team_b: string;
  team_b_id: string;
  p_team_a: number;
  p_team_b: number;
  note: string;
}

export interface MatchupData {
  team_order_names: string[];
  team_order_ids: string[];
  semantics: string;
  bo5: number[][];
  bo7: number[][];
  bo5_bo7_max_abs_difference: number;
  stage1_ledger: LedgerRow[];
}

export interface RuleRef {
  id: string;
  rule: string;
  verification_status: string;
  source: string;
  source_date: string;
}

export type StageKey = "stage1" | "breakthrough" | "knockout" | "final";

export interface StructureStage {
  key: StageKey;
  dates: [string, string];
  format: string;
  teams: number;
  rules: RuleRef[];
}

export type TerminalKey = "STAGE1" | "BREAKTHROUGH" | "LB_R1" | "LB_R2" | "LB_SF" | "LB_F" | "FINAL" | "CHAMPION";

export interface SimTeam {
  id: string;
  official_name: string;
  group: Group;
  p_direct_knockout: number;
  p_breakthrough: number;
  p_stage1_elimination: number;
  p_breakthrough_win: number;
  p_breakthrough_win_given_entry: number;
  p_knockout: number;
  p_upper_semifinal: number;
  p_upper_final: number;
  p_upper_final_win: number;
  p_drop_to_lower: number;
  p_lower_final: number;
  p_final: number;
  p_champion: number;
  p_champion_given_knockout: number;
  terminal: Record<TerminalKey, number>;
  expected_series: number;
  expected_bo7_series: number;
  champion_given_direct: number;
  champion_given_breakthrough: number;
  path_advantage_champion_direct_minus_breakthrough: number;
  p_eliminated_in_breakthrough_given_entry: number;
}

export interface UnresolvedRule {
  rule_name: string;
  verification_status: string;
  classification: string;
  max_delta_championship: number;
  max_delta_final: number;
  max_delta_knockout: number;
}

export interface TournamentData {
  structure: {
    label: string;
    stages: StructureStage[];
    stage1_venue: { value: string; verification_status: string; source: string };
    final_venue: { value: string; verification_status: string; source: string };
    knockout_bracket: Record<string, { date: string; a: string; b: string }>;
  };
  simulated: { label: string; primary_scenario: Record<string, string>; teams: SimTeam[] };
  unresolved_rules: UnresolvedRule[];
}

export interface BenchmarkModel {
  model_id: string;
  n: number;
  log_loss: number;
  brier: number;
  accuracy: number;
  roc_auc: number;
  calibration_slope: number | null;
  mechanism: string | null;
}

export interface BenchmarkFold {
  fold_id: string;
  train_seasons: string[];
  validation_season: string;
  train_start: string;
  train_end: string;
  validation_start: string;
  validation_end: string;
  n_train: number;
  n_validation: number;
  coverage_warning: string | null;
  b5_log_loss: number | null;
  b0_log_loss: number | null;
}

export interface MethodologyData {
  benchmark: { data_version: string; oos_series: number; models: BenchmarkModel[]; folds: BenchmarkFold[] };
  prospective: {
    annual_finals_outcome_rows: number;
    post_cutoff_competitive_rows: number;
    primary_probability_transform: string;
    bo7_correction_in_primary: boolean;
    roster_adjustment_in_primary: boolean;
    draft_adjustment_in_primary: boolean;
    n_simulations: number;
  };
  game_draft_decisions: { layer: string; decision: string }[];
  bo7_audit_decision: string;
  player_model_recommendation: string | null;
  freeze: {
    freeze_id: string;
    information_cutoff: string;
    freeze_date: string;
    first_match: string;
    tests: string;
    tests_passed: number;
    test_count: number;
    git_tag: string;
    primary: string;
  };
}
