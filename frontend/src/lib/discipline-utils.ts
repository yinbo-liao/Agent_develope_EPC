/** Shared discipline utilities — single source of truth for discipline-related logic. */

export const DISCIPLINE_ID_TO_NAME: Record<number, string> = {
  1: 'STRUCTURAL',
  2: 'PIPING',
  3: 'MECHANICAL',
  4: 'ELECTRICAL',
  5: 'HVAC',
};

export const DISCIPLINE_NAME_TO_ID: Record<string, number> = {
  STRUCTURAL: 1, structural: 1,
  PIPING: 2, piping: 2,
  MECHANICAL: 3, mechanical: 3,
  ELECTRICAL: 4, electrical: 4,
  HVAC: 5, hvac: 5,
};

export function disciplineIdFromName(name: string): number {
  const id = DISCIPLINE_NAME_TO_ID[name?.toUpperCase() ?? ''] ?? DISCIPLINE_NAME_TO_ID[name?.toLowerCase() ?? ''];
  return id ?? 0;
}

export function disciplineNameFromId(id: number): string {
  return DISCIPLINE_ID_TO_NAME[id] ?? 'UNKNOWN';
}

/** Disciplines that typically have material items (not just drawings). */
const MATERIAL_DISCIPLINE_NAMES = new Set(['STRUCTURAL', 'PIPING']);

/** Disciplines that typically have equipment items. */
const EQUIPMENT_DISCIPLINE_NAMES = new Set(['MECHANICAL', 'ELECTRICAL', 'HVAC']);

export function isMaterialDiscipline(name: string): boolean {
  return MATERIAL_DISCIPLINE_NAMES.has(name?.toUpperCase() ?? '');
}

export function isEquipmentDiscipline(name: string): boolean {
  return EQUIPMENT_DISCIPLINE_NAMES.has(name?.toUpperCase() ?? '');
}

/** Priority ordering for material categories (used in procurement planning tables). */
export const STRUCTURAL_CATEGORY_ORDER: Record<string, number> = {
  'Steel Plate': 0, 'Bulb Plate': 1, 'Angle Bar': 2, 'I-BEAM': 3, 'FlatBar': 4, 'Pipe': 5,
};

export const PIPING_TYPE_ORDER: Record<string, number> = {
  'Pipe': 0, 'Flange': 1, 'Elbow': 2, 'Tee': 3, 'Reducer': 4, 'Blank': 5, 'Bellow': 6,
  'Bolt/Nuts': 7, 'Weldolet': 8,
};

export const MATERIAL_CATEGORY_ORDER: Record<string, number> = {
  'CS': 0, 'SS': 1, 'DSS': 2, 'CUNI': 3, 'GRE': 4, 'TI': 5,
};

/** Color palette for discipline badges/charts. */
export const DISCIPLINE_COLORS: Record<string, string> = {
  STRUCTURAL: '#f97316',
  PIPING: '#3b82f6',
  MECHANICAL: '#22c55e',
  ELECTRICAL: '#eab308',
  HVAC: '#06b6d4',
};
