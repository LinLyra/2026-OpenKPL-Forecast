#!/usr/bin/env node
// One-way adapter: frozen research artifacts (read-only) -> presentation JSON in web/data/generated/.
// It never writes outside web/data/generated/ and never recomputes a probability.
//   node scripts/build-web-data.mjs          regenerate
//   node scripts/build-web-data.mjs --check  verify every recorded source_sha256 still matches the research files
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = resolve(WEB, "..");
const OUT = join(WEB, "data", "generated");
const FILES = ["forecast", "teams", "matchups", "tournament", "methodology"];

const buf = (rel) => readFileSync(join(ROOT, rel));
const sha256 = (rel) => createHash("sha256").update(buf(rel)).digest("hex");
const text = (rel) => buf(rel).toString("utf8").replace(/^\uFEFF/, "");
const json = (rel) => JSON.parse(text(rel));

function parseCsv(rel) {
  const s = text(rel);
  const rows = [];
  let row = [], field = "", q = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) {
      if (c === '"' && s[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') q = false;
      else field += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && s[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
    } else field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const [head, ...body] = rows;
  return body.map((r) => Object.fromEntries(head.map((h, j) => [h, r[j] ?? ""])));
}

const num = (v) => (v === "" || v === undefined ? null : Number(v));
const slug = (canonical) => canonical.replace(/^TEAM_/, "").toLowerCase().replace(/_/g, "-");

function envelope(sources, data) {
  return {
    source_file: sources,
    source_sha256: sources.map(sha256),
    generated_at: new Date().toISOString(),
    generator: "web/scripts/build-web-data.mjs (read-only adapter; no recomputation)",
    data,
  };
}

// ------------------------------------------------------------------------------------------ sources
const S = {
  primary: "freeze/v1.0/PRIMARY_FORECAST.csv",
  manifest: "freeze/v1.0/FREEZE_MANIFEST.json",
  verification: "freeze/v1.0/POST_FREEZE_VERIFICATION.json",
  rules: "config/2026_annual_finals_rules.yaml",
  stage1: "reports/tournament/stage1_forecast.csv",
  knockout: "reports/tournament/knockout_forecast.csv",
  path: "reports/tournament/path_metrics.csv",
  breakthrough: "reports/tournament/breakthrough_scenarios.csv",
  rotation: "reports/tournament/master_rotation_readiness.csv",
  bo5: "reports/tournament/bo5_matchup_matrix.csv",
  bo7: "reports/tournament/bo7_matchup_matrix.csv",
  ledger: "reports/tournament/PREDICTION_LEDGER_2026.csv",
  materiality: "reports/tournament/rule_materiality_v10a.csv",
  benchmark: "reports/benchmark/v2026_09_28/temporal_metrics.csv",
  folds: "reports/benchmark/v2026_09_28/temporal_folds.csv",
  seasonMetrics: "reports/benchmark/v2026_09_28/season_metrics.csv",
  benchmarkReport: "reports/benchmark/v2026_09_28/temporal_benchmark.md",
  gameDraft: "reports/game_draft_model/v06_game_draft_benchmark.md",
  bo7audit: "reports/bo7_audit/run_summary.json",
  playerModel: "reports/player_model/v05_player_roster_benchmark.md",
};

function build() {
  const manifest = json(S.manifest);
  const verification = json(S.verification);
  const rules = parseYaml(text(S.rules));
  if (sha256(S.primary) !== manifest.primary_forecast_sha256) {
    throw new Error("PRIMARY_FORECAST.csv does not match the freeze manifest hash; refusing to build");
  }

  const seeds = {};
  for (const g of ["master", "elite"]) for (const t of rules.teams[g]) seeds[t.official_name] = t.seed;

  // ---------------------------------------------------------------- forecast.json
  const primary = parseCsv(S.primary);
  const forecastTeams = primary.map((r) => ({
    id: slug(r.canonical_team_id),
    canonical_team_id: r.canonical_team_id,
    official_name: r.team,
    group: r.group,
    seed: seeds[r.team] ?? null,
    frozen_b5_rating: num(r.frozen_b5_rating),
    direct_knockout_probability: num(r.direct_knockout_probability),
    breakthrough_probability: num(r.breakthrough_probability),
    stage1_elimination_probability: num(r.stage1_elimination_probability),
    breakthrough_win_probability: num(r.breakthrough_win_probability),
    knockout_probability: num(r.knockout_probability),
    upper_semifinal_probability: num(r.upper_semifinal_probability),
    upper_final_probability: num(r.upper_final_probability),
    drop_to_lower_bracket_probability: num(r.drop_to_lower_bracket_probability),
    lower_final_probability: num(r.lower_final_probability),
    final_probability: num(r.final_probability),
    championship_probability: num(r.championship_probability),
    mc_se_knockout: num(r.mc_se_knockout),
    mc_se_final: num(r.mc_se_final),
    mc_se_champion: num(r.mc_se_champion),
    n_simulations: num(r.n_simulations),
    sensitivity_only: {
      championship_probability_conservative: num(r.championship_probability_conservative),
      championship_probability_aggressive: num(r.championship_probability_aggressive),
      championship_probability_bo7_sensitivity: num(r.championship_probability_bo7_sensitivity),
    },
  }));
  const championSum = forecastTeams.reduce((a, t) => a + t.championship_probability, 0);
  const freeze = {
    freeze_id: manifest.freeze_id,
    forecast_status: manifest.forecast_status,
    provisional_scope: manifest.provisional_scope,
    created_at: manifest.created_at,
    information_cutoff: manifest.information_cutoff,
    first_scheduled_match: manifest.first_scheduled_match,
    model_version: manifest.model_version,
    data_version: manifest.data_version,
    git_tag: verification.git_tag,
    git_commit_tagged: verification.git_commit,
    git_commit_content: manifest.git_commit,
    strength_file: manifest.strength_file,
    strength_sha256: manifest.strength_sha256,
    primary_forecast: manifest.primary_forecast,
    primary_forecast_sha256: manifest.primary_forecast_sha256,
    prediction_ledger: manifest.prediction_ledger,
    prediction_ledger_content_sha256: manifest.prediction_ledger_content_sha256_excluding_generated_at,
    freeze_manifest_sha256: sha256(S.manifest),
    test_count: verification.test_count,
    tests_passed: verification.tests_passed,
    n_simulations: forecastTeams[0].n_simulations,
  };
  const forecast = envelope([S.primary, S.manifest, S.verification, S.rules], {
    freeze,
    championship_probability_sum: championSum,
    label: primary[0].label,
    teams: forecastTeams,
  });

  // ---------------------------------------------------------------- teams.json
  const byName = Object.fromEntries(forecastTeams.map((t) => [t.official_name, t]));
  const stage1 = Object.fromEntries(parseCsv(S.stage1).map((r) => [r.team, r]));
  const rotation = parseCsv(S.rotation);
  const teams = envelope([S.primary, S.stage1, S.rotation, S.rules], {
    teams: forecastTeams.map((t) => {
      const s = stage1[t.official_name];
      const rot = rotation.filter((r) => r.team === t.official_name).map((r) => ({
        window: r.window,
        series_observed: num(r.series_observed),
        mean_players_used_per_series: num(r.mean_players_used_per_series),
        freq_series_at_least_6_players: num(r.freq_series_at_least_6_players),
        freq_series_at_least_7_players: num(r.freq_series_at_least_7_players),
        max_players_used_in_a_series: num(r.max_players_used_in_a_series),
        label: r.label,
        note: r.note,
      }));
      return {
        id: t.id, canonical_team_id: t.canonical_team_id, official_name: t.official_name, group: t.group, seed: t.seed,
        frozen_b5_rating: t.frozen_b5_rating,
        expected_series_wins: num(s.expected_series_wins),
        expected_game_diff: num(s.expected_game_diff),
        p_group_rank: [1, 2, 3, 4, 5, 6].map((k) => num(s[`p_group_rank_${k}`])),
        historical_roster_usage_descriptive: rot,
      };
    }),
  });

  // ---------------------------------------------------------------- matchups.json
  const matrix = (rel) => {
    const rows = parseCsv(rel);
    const cols = Object.keys(rows[0]).slice(1);
    return { order: cols, p: rows.map((r) => cols.map((c) => num(r[c]))) };
  };
  const m5 = matrix(S.bo5), m7 = matrix(S.bo7);
  let maxFormatDiff = 0;
  m5.p.forEach((row, i) => row.forEach((v, j) => { maxFormatDiff = Math.max(maxFormatDiff, Math.abs(v - m7.p[i][j])); }));
  const ledger = parseCsv(S.ledger).map((r) => ({
    ledger_key: r.ledger_key, stage: r.stage, scheduled_date: r.scheduled_date, format: r.format,
    team_a: r.team_a, team_a_id: slug(r.team_a_id), team_b: r.team_b, team_b_id: slug(r.team_b_id),
    p_team_a: num(r.p_team_a), p_team_b: num(r.p_team_b), note: r.note,
  }));
  const matchups = envelope([S.bo5, S.bo7, S.ledger, S.primary], {
    team_order_names: m5.order,
    team_order_ids: m5.order.map((n) => byName[n].id),
    semantics: "p[i][j] = probability that row team i beats column team j in a series (raw frozen B5, no BO7 correction)",
    bo5: m5.p,
    bo7: m7.p,
    bo5_bo7_max_abs_difference: maxFormatDiff,
    stage1_ledger: ledger,
  });

  // ---------------------------------------------------------------- tournament.json
  const ko = Object.fromEntries(parseCsv(S.knockout).map((r) => [r.team, r]));
  const pm = Object.fromEntries(parseCsv(S.path).map((r) => [r.team, r]));
  const bt = Object.fromEntries(parseCsv(S.breakthrough).map((r) => [r.team, r]));
  const ruleById = Object.fromEntries(rules.rules.map((r) => [r.id, r]));
  const pickRule = (id) => ({ id, rule: ruleById[id].rule, verification_status: ruleById[id].verification_status,
    source: ruleById[id].source, source_date: ruleById[id].source_date });
  const tournament = envelope([S.rules, S.knockout, S.path, S.breakthrough, S.stage1, S.manifest, S.primary], {
    structure: {
      label: "ACTUAL TOURNAMENT STRUCTURE (official 2026 format; realized bracket unknown at freeze)",
      stages: [
        { key: "stage1", dates: ["2026-10-02", "2026-10-18"], format: "BO5", teams: 12, rules: ["R02_STAGE_DATES", "R03_STAGE1_FORMAT", "R05_STAGE1_ADVANCEMENT", "R07_MASTER_ROTATION"].map(pickRule) },
        { key: "breakthrough", dates: ["2026-10-20", "2026-10-22"], format: "BO7", teams: 6, rules: ["R08_BREAKTHROUGH_FORMAT", "R09_BREAKTHROUGH_SELECTION", "R10_BREAKTHROUGH_SELECTION_DETAIL"].map(pickRule) },
        { key: "knockout", dates: ["2026-10-27", "2026-11-08"], format: "BO7", teams: 8, rules: ["R11_KNOCKOUT_FORMAT", "R12_KNOCKOUT_BRACKET_WIRING", "R13_KNOCKOUT_DRAW"].map(pickRule) },
        { key: "final", dates: ["2026-11-14", "2026-11-14"], format: "BO7", teams: 2, rules: ["R14_FINAL"].map(pickRule) },
      ],
      stage1_venue: { value: "广州体育馆2号馆, 广州", verification_status: "VERIFIED_OFFICIAL_2026", source: "reports/tournament/rule_source_registry.csv (GATE_A_STAGE1_VENUE)" },
      final_venue: { value: "五粮液文化体育中心综合体育馆, 成都", verification_status: ruleById.R14_FINAL.verification_status, source: "config/2026_annual_finals_rules.yaml R14_FINAL notes" },
      knockout_bracket: Object.fromEntries(Object.entries(rules.knockout_bracket).filter(([k]) => k !== "format")),
    },
    simulated: {
      label: "SIMULATED FUTURE PATHS (1,000,000 simulations of the official format; PRIMARY scenario)",
      primary_scenario: rules.scenarios.primary,
      teams: forecastTeams.map((t) => {
        const k = ko[t.official_name], p = pm[t.official_name], b = bt[t.official_name];
        return {
          id: t.id, official_name: t.official_name, group: t.group,
          p_direct_knockout: t.direct_knockout_probability,
          p_breakthrough: t.breakthrough_probability,
          p_stage1_elimination: t.stage1_elimination_probability,
          p_breakthrough_win: t.breakthrough_win_probability,
          p_breakthrough_win_given_entry: num(b.p_bt_win_given_bt__PRIMARY),
          p_knockout: t.knockout_probability,
          p_upper_semifinal: num(k.p_upper_semifinal),
          p_upper_final: num(k.p_upper_final),
          p_upper_final_win: num(k.p_upper_final_win),
          p_drop_to_lower: num(k.p_drop_to_lower),
          p_lower_final: num(k.p_lower_final),
          p_final: t.final_probability,
          p_champion: t.championship_probability,
          p_champion_given_knockout: num(k.p_champion_given_knockout),
          terminal: Object.fromEntries(["STAGE1", "BREAKTHROUGH", "LB_R1", "LB_R2", "LB_SF", "LB_F", "FINAL", "CHAMPION"].map((x) => [x, num(k[`p_terminal_${x}`])])),
          expected_series: num(p.expected_series),
          expected_bo7_series: num(p.expected_bo7),
          champion_given_direct: num(p.champion_given_direct),
          champion_given_breakthrough: num(p.champion_given_breakthrough),
          path_advantage_champion_direct_minus_breakthrough: num(p.PATH_ADVANTAGE_champion_direct_minus_breakthrough),
          p_eliminated_in_breakthrough_given_entry: num(p.PATH_COST_p_eliminated_in_breakthrough_given_entry),
        };
      }),
    },
    unresolved_rules: manifest.unresolved_rules.map((u) => ({
      rule_name: u.rule_name, verification_status: u.verification_status, classification: u.classification,
      max_delta_championship: u.max_delta_championship, max_delta_final: u.max_delta_final, max_delta_knockout: u.max_delta_knockout,
    })),
  });

  // ---------------------------------------------------------------- methodology.json
  const bench = parseCsv(S.benchmark).map((r) => ({
    model_id: r.model_id, n: num(r.n), log_loss: num(r.log_loss), brier: num(r.brier), accuracy: num(r.accuracy),
    roc_auc: num(r.roc_auc), calibration_slope: num(r.calibration_slope),
  }));
  const gd = text(S.gameDraft);
  const decisionRows = gd.slice(gd.indexOf("## Decision")).split("\n")
    .filter((l) => l.startsWith("| ") && !l.startsWith("| layer") && !l.startsWith("|---"))
    .map((l) => l.split("|").slice(1, -1).map((x) => x.trim()))
    .map(([layer, decision]) => ({ layer, decision }));
  const bo7 = json(S.bo7audit);
  const pmText = text(S.playerModel);
  const report = text(S.benchmarkReport);
  const mechanisms = Object.fromEntries(
    report.slice(report.indexOf("| model | mechanism |")).split("\n").slice(2)
      .filter((l) => /^\| B\d \|/.test(l))
      .map((l) => l.split("|").slice(1, -1).map((x) => x.trim())),
  );
  const seasonRows = parseCsv(S.seasonMetrics);
  const folds = parseCsv(S.folds).map((f) => {
    const season = (id) => seasonRows.find((r) => r.model_id === id && r.season === f.validation_season);
    return {
      fold_id: f.fold_id,
      train_seasons: f.train_seasons.split("|"),
      validation_season: f.validation_season,
      train_start: f.train_start, train_end: f.train_end,
      validation_start: f.validation_start, validation_end: f.validation_end,
      n_train: num(f.n_train), n_validation: num(f.n_validation),
      coverage_warning: f.coverage_warning || null,
      b5_log_loss: num(season("B5")?.log_loss), b0_log_loss: num(season("B0")?.log_loss),
    };
  });
  const checks = manifest.pre_freeze_checks;
  const methodology = envelope([S.benchmark, S.folds, S.seasonMetrics, S.benchmarkReport, S.gameDraft, S.bo7audit, S.playerModel, S.manifest, S.verification], {
    benchmark: {
      data_version: "v2026_09_28", oos_series: bench[0].n,
      models: bench.map((m) => ({ ...m, mechanism: mechanisms[m.model_id] ?? null })),
      folds,
    },
    prospective: {
      annual_finals_outcome_rows: checks.annual_finals_outcome_rows,
      post_cutoff_competitive_rows: checks.post_cutoff_competitive_rows,
      primary_probability_transform: checks.primary_probability_transform,
      bo7_correction_in_primary: checks.bo7_correction_in_primary,
      roster_adjustment_in_primary: checks.roster_adjustment_in_primary,
      draft_adjustment_in_primary: checks.draft_adjustment_in_primary,
      n_simulations: forecastTeams[0].n_simulations,
    },
    game_draft_decisions: decisionRows,
    bo7_audit_decision: bo7.decision,
    player_model_recommendation: pmText.includes("Keep **B5** as the deployable reference") ? "Keep B5 as the deployable reference; do not carry B6–B12 forward" : null,
    freeze: {
      freeze_id: manifest.freeze_id,
      information_cutoff: manifest.information_cutoff,
      freeze_date: manifest.created_at.slice(0, 10),
      first_match: manifest.first_scheduled_match.slice(0, 10),
      tests: `${verification.tests_passed} / ${verification.test_count}`,
      tests_passed: verification.tests_passed,
      test_count: verification.test_count,
      git_tag: verification.git_tag,
      primary: "RAW B5",
    },
  });

  return { forecast, teams, matchups, tournament, methodology };
}

// ------------------------------------------------------------------------------------------ main
if (process.argv.includes("--check")) {
  let bad = 0;
  for (const f of FILES) {
    const p = join(OUT, `${f}.json`);
    if (!existsSync(p)) { console.error(`missing ${p}`); bad++; continue; }
    const g = JSON.parse(readFileSync(p, "utf8"));
    g.source_file.forEach((rel, i) => {
      const ok = sha256(rel) === g.source_sha256[i];
      if (!ok) bad++;
      console.log(`${ok ? "OK  " : "DIFF"} ${f}.json <- ${rel}`);
    });
  }
  process.exit(bad ? 1 : 0);
} else {
  const out = build();
  mkdirSync(OUT, { recursive: true });
  for (const f of FILES) writeFileSync(join(OUT, `${f}.json`), JSON.stringify(out[f], null, 2) + "\n");
  console.log(`wrote ${FILES.map((f) => `data/generated/${f}.json`).join(", ")}`);
  console.log(`championship probability sum = ${out.forecast.data.championship_probability_sum}`);
}
