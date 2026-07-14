import { FACULTIES, programmesForFaculty } from '../../constants/faculties';

export default function FacultyProgrammeFields({ faculty, programme, onChange }) {
  const programmes = programmesForFaculty(faculty);

  return (
    <>
      <label>
        Faculty
        <select
          name="faculty"
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
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Programme
        <select
          name="programme"
          value={programme}
          onChange={(e) => onChange({ programme: e.target.value })}
          required
          disabled={!faculty}
        >
          <option value="">{faculty ? 'Select programme' : 'Choose faculty first'}</option>
          {programmes.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
