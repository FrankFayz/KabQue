import { useMemo, useState } from 'react';
import Panel from '../ui/Panel';

function share(count, total) {
  if (!total) return 0;
  return Math.round((count / total) * 100);
}

function FacultyRows({ rows, total }) {
  const max = Math.max(...rows.map((r) => r.count), 1);

  return (
    <ul className="dist-list">
      {rows.map((row, index) => {
        const count = row.count ?? 0;
        const pct = share(count, total);
        const width = Math.max(8, Math.round((count / max) * 100));
        return (
          <li key={row.faculty || `faculty-${index}`} className="dist-row">
            <div className="dist-row-head">
              <div className="dist-text">
                <span className="dist-label">{row.faculty || 'Unspecified'}</span>
              </div>
              <span className="dist-meta">
                <strong>{count}</strong>
                <span className="dist-pct">{pct}%</span>
              </span>
            </div>
            <div className="dist-track" aria-hidden="true">
              <span
                className={`dist-fill dist-fill-${(index % 3) + 1}`}
                style={{ width: `${width}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function groupProgrammesByFaculty(byFaculty = [], byProgramme = []) {
  const map = new Map();

  for (const row of byFaculty) {
    const key = row.faculty || '';
    map.set(key, {
      faculty: key,
      count: row.count || 0,
      programmes: [],
    });
  }

  for (const row of byProgramme) {
    const key = row.faculty || '';
    if (!map.has(key)) {
      map.set(key, {
        faculty: key,
        count: 0,
        programmes: [],
      });
    }
    const group = map.get(key);
    group.programmes.push({
      programme: row.programme || '',
      count: row.count || 0,
    });
    // Recalc faculty total from programmes when faculty row was missing
    if (!byFaculty.some((f) => (f.faculty || '') === key)) {
      group.count += row.count || 0;
    }
  }

  for (const group of map.values()) {
    group.programmes.sort((a, b) => b.count - a.count || a.programme.localeCompare(b.programme));
  }

  return Array.from(map.values()).sort(
    (a, b) => b.count - a.count || a.faculty.localeCompare(b.faculty)
  );
}

function FacultyProgrammeAccordion({ groups, total }) {
  const [openFaculty, setOpenFaculty] = useState(null);

  function toggle(facultyKey) {
    setOpenFaculty((prev) => (prev === facultyKey ? null : facultyKey));
  }

  return (
    <ul className="faculty-accordion">
      {groups.map((group, index) => {
        const key = group.faculty || `unspecified-${index}`;
        const isOpen = openFaculty === key;
        const facultyPct = share(group.count, total);
        const panelId = `faculty-panel-${index}`;
        const maxProg = Math.max(...group.programmes.map((p) => p.count), 1);

        return (
          <li key={key} className={`faculty-acc-item${isOpen ? ' is-open' : ''}`}>
            <button
              type="button"
              className="faculty-acc-trigger"
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => toggle(key)}
            >
              <span className="faculty-acc-main">
                <span className="faculty-acc-chevron" aria-hidden="true" />
                <span className="dist-text">
                  <span className="dist-label">{group.faculty || 'Unspecified'}</span>
                  <span className="dist-sub">
                    {group.programmes.length} programme
                    {group.programmes.length === 1 ? '' : 's'}
                  </span>
                </span>
              </span>
              <span className="dist-meta">
                <strong>{group.count}</strong>
                <span className="dist-pct">{facultyPct}%</span>
              </span>
            </button>

            <div
              id={panelId}
              className="faculty-acc-panel"
              hidden={!isOpen}
            >
              {group.programmes.length === 0 ? (
                <p className="faculty-acc-empty">No programmes in this faculty yet.</p>
              ) : (
                <ul className="programme-list">
                  {group.programmes.map((prog, pIndex) => {
                    const width = Math.max(
                      8,
                      Math.round((prog.count / maxProg) * 100)
                    );
                    const pctOfFaculty = share(prog.count, group.count);
                    return (
                      <li
                        key={`${key}-${prog.programme}-${pIndex}`}
                        className="programme-row"
                      >
                        <div className="dist-row-head">
                          <span className="programme-name">
                            {prog.programme || 'Unspecified programme'}
                          </span>
                          <span className="dist-meta">
                            <strong>{prog.count}</strong>
                            <span className="dist-pct">{pctOfFaculty}%</span>
                          </span>
                        </div>
                        <div className="dist-track" aria-hidden="true">
                          <span
                            className={`dist-fill dist-fill-${(pIndex % 3) + 1}`}
                            style={{ width: `${width}%` }}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default function AnalyticsBreakdown({
  byFaculty = [],
  byProgramme = [],
  totalInQueue = 0,
}) {
  const queueTotal =
    totalInQueue ||
    byFaculty.reduce((sum, row) => sum + (row.count || 0), 0);

  const groups = useMemo(
    () => groupProgrammesByFaculty(byFaculty, byProgramme),
    [byFaculty, byProgramme]
  );

  return (
    <div className="analytics-grid">
      <Panel title="Faculty in queue" className="analytics-panel">
        <div className="analytics-head">
          <p className="analytics-kicker">Live queue totals</p>
          <span className="analytics-total">{queueTotal}</span>
        </div>
        {byFaculty.length === 0 ? (
          <div className="analytics-empty">
            <strong>Queue is empty</strong>
            <p>Faculty counts appear only for students currently in KabQue.</p>
          </div>
        ) : (
          <FacultyRows rows={byFaculty} total={queueTotal} />
        )}
      </Panel>

      <Panel title="Programmes by faculty" className="analytics-panel">
        <div className="analytics-head">
          <p className="analytics-kicker">Tap a faculty to see programmes</p>
          <span className="analytics-total">{queueTotal}</span>
        </div>
        {groups.length === 0 ? (
          <div className="analytics-empty">
            <strong>Queue is empty</strong>
            <p>Open a faculty after students join to see programme counts.</p>
          </div>
        ) : (
          <FacultyProgrammeAccordion groups={groups} total={queueTotal} />
        )}
      </Panel>
    </div>
  );
}
