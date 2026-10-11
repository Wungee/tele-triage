import { useEffect, useRef } from "react";

const NAMES = {
  ALL: "All alarms",
  Asystole: "Asystole",
  Bradycardia: "Extreme brady",
  Tachycardia: "Extreme tachy",
  Ventricular_Tachycardia: "V-tach",
  Ventricular_Flutter_Fib: "V-fib / flutter",
};

const pct = (v) => (v === null || v === undefined ? "n/a" : `${v.toFixed(0)}%`);

export default function ModelCard({ card, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const rep = card?.report;
  const test = rep?.test || {};
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="How well the co-pilot does">
      <div className="modal__box">
        <header className="modal__head">
          <h2>How well the co-pilot does</h2>
          <button ref={ref} className="btn btn--ghost" onClick={onClose}>
            Close
          </button>
        </header>
        {card?.synthetic && (
          <p className="warn">These numbers come from synthetic test data. Train on PhysioNet before presenting.</p>
        )}
        <p className="modal__lede">
          Measured on {rep?.n_test} alarms held out from training ({card?.dataset}). Every alarm on the wall comes
          from this held-out set, so the model has never seen any of them.
        </p>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Alarm</th>
                <th>True / false</th>
                <th>False alarms labelled artifact</th>
                <th>True alarms labelled artifact</th>
                <th>AUC</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(test).map(([k, m]) => (
                <tr key={k}>
                  <td>{NAMES[k] || k}</td>
                  <td>
                    {m.n_true} / {m.n_false}
                  </td>
                  <td>
                    {m.false_alarms_flagged_artifact} ({pct(m.pct_false_alarms_flagged)})
                  </td>
                  <td className={m.true_alarms_flagged_artifact ? "bad" : ""}>
                    {m.true_alarms_flagged_artifact} ({pct(m.pct_true_alarms_flagged)})
                  </td>
                  <td>{m.auc === null ? "n/a" : m.auc.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="modal__note">
          "Likely artifact" is only shown below a cut-off chosen so that, in cross-validation, at most{" "}
          {Math.round((rep?.target_miss ?? 0.01) * 100)}% of true alarms would get that label. Missing a real alarm
          costs more than reviewing a false one, so the model is tuned that way.
        </p>
      </div>
    </div>
  );
}
