/** Kabale University faculties and sample programmes for registration analytics. */
export const FACULTIES = [
  {
    name: 'Faculty of Education',
    programmes: [
      'Bachelor of Education (Arts)',
      'Bachelor of Education (Science)',
      'Bachelor of Education Primary',
      'Diploma in Education Primary',
    ],
  },
  {
    name: 'Faculty of Science',
    programmes: [
      'Bachelor of Science',
      'Bachelor of Science with Education',
      'Bachelor of Science in Agriculture',
    ],
  },
  {
    name: 'Faculty of Arts and Social Sciences',
    programmes: [
      'Bachelor of Arts',
      'Bachelor of Social Work and Social Administration',
      'Bachelor of Public Administration',
    ],
  },
  {
    name: 'Faculty of Computing, Library and Information Science',
    programmes: [
      'Bachelor of Computer Science',
      'Bachelor of Information Technology',
      'Bachelor of Library and Information Science',
      'Diploma in Computer Science',
    ],
  },
  {
    name: 'Faculty of Economics and Management Sciences',
    programmes: [
      'Bachelor of Business Administration',
      'Bachelor of Economics',
      'Bachelor of Procurement and Logistics',
      'Diploma in Business Administration',
    ],
  },
  {
    name: 'Faculty of Engineering, Technology, Applied Design and Fine Art',
    programmes: [
      'Bachelor of Civil Engineering',
      'Bachelor of Electrical Engineering',
      'Bachelor of Mechanical Engineering',
      'Bachelor of Fine Art',
    ],
  },
  {
    name: 'Faculty of Agriculture and Environmental Sciences',
    programmes: [
      'Bachelor of Agriculture',
      'Bachelor of Environmental Science',
      'Bachelor of Agribusiness',
    ],
  },
  {
    name: 'School of Medicine',
    programmes: [
      'Bachelor of Medicine and Bachelor of Surgery',
      'Bachelor of Nursing Science',
      'Diploma in Clinical Medicine',
    ],
  },
];

export function programmesForFaculty(facultyName) {
  const faculty = FACULTIES.find((f) => f.name === facultyName);
  return faculty?.programmes ?? [];
}
