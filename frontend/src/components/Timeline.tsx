import { Link } from "react-router-dom";
import type { AgendaDay, AgendaItem } from "../lib/agenda";
import { formatDay, formatTime, relativeDay, toNaiveIso } from "../lib/time";

const KIND_LABEL: Record<string, string> = {
  class: "Class",
  exam: "Exam",
  training: "Training",
  competition: "Game day",
  travel: "Travel",
  other: "Busy",
};

const isRelative = (date: Date) => ["Today", "Tomorrow"].includes(relativeDay(toNaiveIso(date)));
const dayTitle = (date: Date) => (isRelative(date) ? relativeDay(toNaiveIso(date)) : formatDay(date, "long"));

function ItemBlock({ item }: { item: AgendaItem }) {
  const time = item.end ? `${formatTime(item.start)} – ${formatTime(item.end)}` : formatTime(item.start);
  const base = "border-l-4 px-3 py-2";
  if (item.kind === "session") {
    return (
      <Link to={item.link ?? "/today"} className={`${base} block border-ink bg-whistle hover:brightness-95`}>
        <span className="label !text-ink">Study · {time}</span>
        <span className="block font-display text-2xl font-bold leading-tight">{item.title}</span>
        <span className="text-sm">{item.detail}</span>
      </Link>
    );
  }
  if (item.kind === "due") {
    return (
      <div className={`${base} border-flag bg-flag-soft`}>
        <span className="label !text-flag">Due · {time}</span>
        <span className="block font-display text-xl font-bold leading-tight">{item.title}</span>
      </div>
    );
  }
  const heavy = item.commitmentKind === "training" || item.commitmentKind === "competition";
  return (
    <div className={`${base} hatch ${heavy ? "border-ink" : "border-ink-soft"} bg-paper-2`}>
      <span className="label">
        {KIND_LABEL[item.commitmentKind ?? "other"]} · {time}
      </span>
      <span className="block font-display text-xl font-bold leading-tight">{item.title}</span>
    </div>
  );
}

export function Timeline({ days, emptyLabel = "Nothing scheduled" }: { days: AgendaDay[]; emptyLabel?: string }) {
  return (
    <div className="space-y-6">
      {days.map((day) => (
        <section key={day.key} aria-labelledby={`day-${day.key}`}>
          <h3 id={`day-${day.key}`} className="mb-2 flex items-baseline gap-3 border-b border-line pb-1">
            <span className="text-3xl">{dayTitle(day.date)}</span>
            {isRelative(day.date) && <span className="label">{formatDay(day.date, "short")}</span>}
          </h3>
          {day.items.length === 0 ? (
            <p className="text-ink-soft">{emptyLabel}</p>
          ) : (
            <ol className="space-y-2">
              {day.items.map((item) => (
                <li key={item.key} className="grid grid-cols-[4.5rem_1fr] items-start gap-3">
                  <span className="num pt-2 font-display text-xl font-semibold text-ink-soft">{formatTime(item.start).replace(" ", "\u00a0")}</span>
                  <ItemBlock item={item} />
                </li>
              ))}
            </ol>
          )}
        </section>
      ))}
    </div>
  );
}
