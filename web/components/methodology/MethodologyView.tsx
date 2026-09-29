import { Fragment } from "react";
import { methodology } from "@/lib/data";
import { dict, type Locale } from "@/lib/i18n";
import { Page, PageHeader, Panel } from "@/components/common/ui";

const season = (s: string) => s.replace(/^KPL20/, "");

function Section({ n, title, body, children }: { n: string; title: string; body: string; children?: React.ReactNode }) {
  return (
    <Panel className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-12">
      <div>
        <p className="num text-h1 font-bold text-gold/40">{n}</p>
        <h2 className="mt-2 text-h2 font-semibold">{title}</h2>
        <p className="mt-3 text-body text-mute">{body}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </Panel>
  );
}

export function MethodologyView({ locale }: { locale: Locale }) {
  const t = dict(locale);
  const m = t.method;
  const d = methodology.data;
  const models = d.benchmark.models;
  const folds = d.benchmark.folds;
  const seasons = [...new Set(folds.flatMap((f) => [...f.train_seasons, f.validation_season]))].sort();

  return (
    <Page>
      <PageHeader kicker={m.kicker} title={m.title} lead={m.lead} />
      <div className="mt-10 space-y-6">
        <Section n="01" title={m.concept.title} body={m.concept.body}>
          <ol className="grid h-full gap-3 sm:grid-cols-3">
            {m.concept.points.map((p, i) => (
              <li key={p} className="flex flex-col justify-between rounded-xl bg-ink-850/80 p-5">
                <span className="num text-caption text-gold">0{i + 1}</span>
                <span className="mt-8 text-h3 font-semibold">{p}</span>
              </li>
            ))}
          </ol>
        </Section>

        <Section n="02" title={m.selection.title} body={m.selection.body}>
          <p className="text-caption text-mute">{m.selection.metric}</p>
          <ol className="mt-5 space-y-2">
            {models.map((md, index) => {
              const chosen = md.model_id === "B5";
              const addition = m.selection.additions[md.model_id as keyof typeof m.selection.additions];
              return (
                <li key={md.model_id}>
                  {index > 0 && <p className="ml-5 py-1 text-micro text-gold/70">↓ + {addition}</p>}
                  <div className={`grid grid-cols-[2.75rem_minmax(0,1fr)_4rem] items-center gap-3 rounded-xl px-4 py-3 ${chosen ? "bg-gold/12 ring-1 ring-gold/45" : "bg-ink-850/65"}`}>
                    <span className={`num text-body font-bold ${chosen ? "text-gold" : "text-faint"}`}>{md.model_id}</span>
                    <span className={`text-body ${chosen ? "font-semibold text-fg" : "text-mute"}`}>{m.selection.names[md.model_id as keyof typeof m.selection.names]}</span>
                    <span className={`num text-right text-body ${chosen ? "font-semibold text-gold-soft" : "text-mute"}`}>{md.log_loss.toFixed(3)}</span>
                  </div>
                </li>
              );
            })}
          </ol>
        </Section>

        <Section n="03" title={m.validation.title}
          body={m.validation.body.replace("{folds}", String(folds.length)).replace("{series}", d.benchmark.oos_series.toLocaleString("en-US"))}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[440px] border-separate border-spacing-x-[4px] border-spacing-y-[3px]">
              <tbody>
                {folds.map((f) => (
                  <tr key={f.fold_id}>
                    {seasons.map((s) => {
                      const train = f.train_seasons.includes(s), test = f.validation_season === s;
                      return <td key={s} className={`h-3 rounded-[3px] ${test ? "bg-gold" : train ? "bg-blue/35" : "bg-ink-850"}`} />;
                    })}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  {seasons.map((s) => (
                    <td key={s} className="pt-1.5 text-center text-[9px] tracking-tight text-faint">{season(s)}</td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="mt-3 flex gap-5 text-micro text-mute">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-blue/35" />{m.validation.train}</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-gold" />{m.validation.test}</span>
          </p>
        </Section>

        <Section n="04" title={m.simulation.title} body={m.simulation.body}>
          <div className="flex h-full flex-col justify-center">
            <p className="gold-num text-display leading-none">{d.prospective.n_simulations.toLocaleString("en-US")}</p>
            <p className="mt-2 text-caption text-mute">{m.simulation.sims}</p>
            <ol className="mt-8 flex flex-wrap items-center gap-2 text-body">
              {[t.stages.stage1, t.stages.breakthrough, t.stages.knockout, t.stages.final].map((s, i) => (
                <Fragment key={s}>
                  {i > 0 && <li aria-hidden className="text-gold/60">→</li>}
                  <li className="rounded-full border border-line-strong px-4 py-1.5">{s}</li>
                </Fragment>
              ))}
              <li aria-hidden className="text-gold/60">→</li>
              <li className="rounded-full bg-gradient-to-b from-gold-soft to-gold-deep px-4 py-1.5 font-semibold text-navy">{t.stages.champion}</li>
            </ol>
          </div>
        </Section>

        <div className="pt-4 text-center">
          <div className="gold-rule mx-auto max-w-md" />
          <p className="mt-5 text-caption text-mute">{m.note.replace("{date}", m.date(d.freeze.first_match))}</p>
        </div>
      </div>
    </Page>
  );
}
