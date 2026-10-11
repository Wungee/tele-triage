// Terms and privacy, written for what this app actually does. Keep them true: if you add
// analytics, accounts, or a new third-party service, update these pages in the same commit.

const UPDATED = "October 11, 2026";

function Terms() {
  return (
    <>
      <h1>Terms of use</h1>
      <p className="updated">Last updated {UPDATED}</p>

      <h2>What this is</h2>
      <p>
        Alarm Triage Co-Pilot is a research prototype built at a student hackathon (Hacklanta 2026). It replays
        alarms from a public, de-identified research dataset and shows how software could help a central monitoring
        technician review them.
      </p>

      <h2>Not for clinical use</h2>
      <p>
        This software is not a medical device and has not been cleared or approved by the FDA or any other regulator.
        Do not use it to make or support decisions about any real patient. Its output can be wrong.
      </p>

      <h2>No affiliation</h2>
      <p>
        This project is not affiliated with, sponsored by, or endorsed by any hospital or health system, including the
        author's employer. It uses no data from any hospital.
      </p>

      <h2>Acceptable use</h2>
      <ul>
        <li>Do not upload recordings or any data that could identify a real patient.</li>
        <li>Do not try to disrupt the service, overload it, or access data that is not yours.</li>
      </ul>

      <h2>Data and fonts</h2>
      <p>
        Waveforms come from the PhysioNet/Computing in Cardiology Challenge 2015, "Reducing False Arrhythmia Alarms in
        the ICU", used under the Open Data Commons Attribution License 1.0. Clifford GD, Silva I, Moody B, et al.,
        Computing in Cardiology 2015;42:273-276.
      </p>
      <p>
        Typefaces: Ronzino by Luigi Gorlero and Nunzio Mazzaferro, and Coconat by Sara Lavazza, both published by
        Collletttivo under the SIL Open Font License 1.1.
      </p>

      <h2>No warranty</h2>
      <p>
        The software and this demo are provided as is, without warranty of any kind. The author is not liable for any
        use of it.
      </p>

      <h2>Changes</h2>
      <p>These terms may change. The date at the top shows the latest version.</p>
    </>
  );
}

function Privacy() {
  return (
    <>
      <h1>Privacy</h1>
      <p className="updated">Last updated {UPDATED}</p>

      <h2>No accounts, cookies or tracking</h2>
      <p>
        There are no sign-ups, no cookies, no analytics and no advertising. Fonts are served from this site, so loading
        a page makes no requests to other companies.
      </p>

      <h2>What is stored when you review an alarm</h2>
      <p>When you press one of the decision buttons, the server saves one row with:</p>
      <ul>
        <li>which demo alarm it was and its type</li>
        <li>the co-pilot's score and label</li>
        <li>your decision and how many seconds it took</li>
        <li>the expert label from the dataset</li>
        <li>the time</li>
      </ul>
      <p>
        Nothing in that row identifies you. It powers the counters at the top of the page and is deleted when the demo
        database is reset.
      </p>

      <h2>Server logs</h2>
      <p>
        Like most websites, the server keeps routine request logs (time, page requested and IP address) to keep the
        service running. They are kept only on the server and only while the demo is running.
      </p>

      <h2>Plain-English summaries</h2>
      <p>
        If the summary feature is turned on and you press "Summarize in plain English", the alarm type, the co-pilot's
        label, the measured rates and the evidence text are sent to Google's Gemini API to write the sentence. No
        information about you is included. Google's own terms apply to that request.
      </p>

      <h2>Uploaded recordings</h2>
      <p>
        The scoring API accepts a recording file, processes it in a temporary folder and deletes it immediately after
        scoring. It is never stored. Do not upload anything that could identify a patient.
      </p>

      <h2>Patient data</h2>
      <p>
        None. Every waveform comes from a public research dataset that was de-identified by its publishers before
        release.
      </p>

      <h2>Questions</h2>
      <p>Open an issue on the project's GitHub repository.</p>
    </>
  );
}

export default function Legal({ page }) {
  return (
    <main className="legal">
      <a className="legal__back" href="/">
        Back to the monitoring wall
      </a>
      {page === "privacy" ? <Privacy /> : <Terms />}
    </main>
  );
}
