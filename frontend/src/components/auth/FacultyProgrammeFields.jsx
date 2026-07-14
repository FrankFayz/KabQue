import { FACULTIES, programmesForFaculty } from '../../constants/faculties';

export default function FacultyProgrammeFields({ faculty, programme, onChange }) {
  const programmes = programmesForFaculty(faculty);

  return (
    <div className="academic-fields">
      <label className="academic-field">
        <span className="academic-field-label">Faculty</span>
        <select
          name="faculty"
          className="academic-select"
          value={faculty}
          onChange={(e) =>
            onChange({
              faculty: e.target.value,
              programme: '',
            })
          }
          required
        >
          <option value="">Select faculty</option>
          {FACULTIES.map((f) => (
            <option key={f.name} value={f.name} title={f.name}>
              {f.name}
            </option>
          ))}
        </select>
      </label>
      <label className="academic-field">
        <span className="academic-field-label">Programme</span>
        <select
          name="programme"
          className="academic-select"
          value={programme}
          onChange={(e) => onChange({ programme: e.target.value })}
          required
          disabled={!faculty}
        >
          <option value="">
            {faculty ? 'Select programme' : 'Choose faculty first'}
          </option>
          {programmes.map((p) => (
            <option key={p} value={p} title={p}>
              {p}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
