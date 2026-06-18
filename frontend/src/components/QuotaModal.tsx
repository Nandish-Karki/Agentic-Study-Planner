import { Clock, X } from "lucide-react";

function whenText(retryAt: string | null | undefined): string {
  if (!retryAt) return "in about 24 hours";
  const ms = new Date(retryAt).getTime() - Date.now();
  if (!Number.isFinite(ms) || ms <= 0) return "shortly";
  const h = Math.round(ms / 3_600_000);
  if (h >= 1) return `in about ${h} hour${h === 1 ? "" : "s"}`;
  const m = Math.max(1, Math.round(ms / 60_000));
  return `in about ${m} minute${m === 1 ? "" : "s"}`;
}

// Friendly "free-tier exhausted / daily limit reached" dialog.
export default function QuotaModal({
  message,
  retryAt,
  perUser,
  onClose,
}: {
  message?: string;
  retryAt?: string | null;
  perUser?: boolean; // true = the user's own daily cap; false = our shared free tier
  onClose: () => void;
}) {
  const title = perUser ? "Daily plan limit reached" : "We've hit today's free-tier limit";
  const body =
    message ||
    (perUser
      ? "You've used all your plans for today. Please try again tomorrow."
      : `Our free AI quota is used up right now. Plan generation resumes ${whenText(retryAt)}.`);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-md rounded-2xl border border-white/10 bg-ink p-7 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-slate-500 hover:text-white transition"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-accent/15 text-accent">
            <Clock className="h-6 w-6" />
          </span>
          <h2 className="text-xl font-bold">{title}</h2>
        </div>
        <p className="mt-4 text-slate-300">{body}</p>
        {!perUser && (
          <p className="mt-2 text-sm text-slate-500">
            We run on a shared free tier, so capacity resets daily. Your uploads were not
            stored — nothing to clean up. Come back later and try again.
          </p>
        )}
        <button
          onClick={onClose}
          className="mt-6 w-full rounded-lg bg-accent px-5 py-2.5 font-semibold transition hover:bg-indigo-500"
        >
          Got it
        </button>
      </div>
    </div>
  );
}
