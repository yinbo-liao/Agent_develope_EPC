/** Shared TypeScript interfaces for EPC API responses. */

// ── Core Project ────────────────────────────────────────────────────
export interface Project {
  project_id: string;
  project_code: string;
  project_name: string;
  client_name?: string;
  contract_value?: number;
  planned_start_date: string;
  planned_finish_date: string;
  baseline_start_date?: string;
  baseline_finish_date?: string;
  current_status: string;
  created_at?: string;
}

export interface Activity {
  activity_id: string;
  project_id: string;
  activity_code: string;
  activity_name: string;
  original_duration: number;
  remaining_duration?: number;
  total_float?: number;
  is_critical: boolean;
  physical_percent_complete: number;
  status: string;
  work_scope_category?: string;
  updated_at?: string;
}

export interface DashboardSummary {
  project: Project;
  activities: {
    total: number;
    critical_count: number;
    avg_progress: number;
  };
  alerts: { open_alerts: number };
  ndt: { total: number; avg_pct: number };
}

// ── Engineering ─────────────────────────────────────────────────────
export interface Drawing {
  drawing_id: string;
  project_id: string;
  discipline_id: number;
  drawing_number: string;
  drawing_title?: string;
  drawing_type?: string;
  status: string;
  planned_issue_date?: string;
  actual_issue_date?: string;
  revision?: string;
  weight_kg?: number;
  issued_for_info?: string;
  issued_for_info_date?: string;
  issued_for_construction?: string;
  issued_for_construction_date?: string;
  discipline_name?: string;
}

export interface DrawingMaterial {
  material_id: string;
  drawing_id: string;
  project_id: string;
  piece_mark: string;
  material_grade?: string;
  material_thickness?: string;
  material_weight?: number;
  material_type?: string;
  size?: string;
  diameter?: string;
  material_length?: number;
  material_category?: string;
  total_weight?: number;
  po_status?: string;
  material_class?: string;
  mvr_status: string;
  mvr_confirmed_by?: string;
  mvr_confirmed_at?: string;
  drawing_number?: string;
  drawing_title?: string;
  drawing_rev?: string;
  issued_for_info?: string;
  issued_for_construction?: string;
  discipline_name?: string;
  discipline_id?: number;
  is_afc?: boolean;
  is_afi?: boolean;
  po_id?: string;
  po_number?: string;
}

export interface DrawingEquipment {
  equipment_id: string;
  drawing_id: string;
  project_id: string;
  equipment_tag?: string;
  equipment_name?: string;
  equipment_detail?: string;
  install_location?: string;
  weight?: number;
  equipment_type?: string;
  certification?: string;
  fat_status: string;
  test_status?: string;
  system_code?: string;
  system_name?: string;
  schedule_delivery_date?: string;
  schedule_install_date?: string;
  remark?: string;
  drawing_number?: string;
  drawing_title?: string;
  drawing_rev?: string;
  issued_for_info?: string;
  issued_for_construction?: string;
  discipline_name?: string;
  discipline_id?: number;
  is_afc?: boolean;
  is_afi?: boolean;
}

export interface ProcurementPlanningItem {
  material_category?: string;
  material_type?: string;
  size?: string;
  thickness?: string;
  grade?: string;
  material_class?: string;
  po_status?: string;
  count: number;
  total_length_m?: number;
  total_weight_kg?: number;
}

export interface EquipmentPlanningItem {
  equipment_type: string;
  count: number;
  total_weight_kg: number;
  fat_approved: number;
  fat_pending: number;
}

export interface MaterialsResponse {
  items: DrawingMaterial[];
  procurement_planning: ProcurementPlanningItem[];
}

export interface EquipmentResponse {
  items: DrawingEquipment[];
  procurement_planning: EquipmentPlanningItem[];
}

export interface ChangeSummary {
  drawings_added: number;
  drawings_deleted: number;
  materials_added: number;
  materials_deleted: number;
}

// ── Procurement ─────────────────────────────────────────────────────
export interface PurchaseOrder {
  po_id: string;
  project_id: string;
  po_number: string;
  vendor_name?: string;
  order_date?: string;
  expected_delivery_date?: string;
  actual_delivery_date?: string;
  total_amount?: number;
  status: string;
}

export interface PurchaseItem {
  purchase_item_id: string;
  po_id: string;
  material_type?: string;
  material_spec?: string;
  quantity_ordered: number;
  unit?: string;
  unit_price?: number;
  quantity_received?: number;
  received_date?: string;
}

// ── Construction ────────────────────────────────────────────────────
export interface ConstructionMaterialsResponse {
  materials: DrawingMaterial[];
  equipment: DrawingEquipment[];
}

export interface MVRSummaryItem {
  discipline_name: string;
  total_materials: number;
  info_afi_count: number;
  structure_requested_count: number;
  mvr_confirm_count: number;
}

export interface WeeklyPlanningTask {
  task_id: string;
  project_id: string;
  week_start: string;
  activity_id?: string;
  planned_status: string;
  planned_completion_percent: number;
  actual_completion_percent?: number;
  is_completed: boolean;
  delay_reason?: string;
  accountability_party?: string;
  activity_name?: string;
}

export interface ResourceShortage {
  shortage_id: string;
  project_id: string;
  shortage_type: string;
  resource_name: string;
  required_quantity: number;
  available_quantity: number;
  shortfall: number;
  expected_resolution_date?: string;
  impact_description?: string;
  status: string;
}

// ── System Completion ───────────────────────────────────────────────
export interface SubSystem {
  sub_system_id: string;
  project_id: string;
  system_code: string;
  system_name?: string;
  parent_system_id?: string;
  discipline_id?: number;
  area_code?: string;
  completion_status: string;
  planned_mc_date?: string;
  actual_mc_date?: string;
  handover_date?: string;
  responsible_engineer?: string;
  notes?: string;
  discipline_name?: string;
  open_punch_count?: number;
}

export interface PunchItem {
  punch_id: string;
  project_id: string;
  sub_system_id: string;
  punch_number: string;
  category: 'A' | 'B' | 'C';
  discipline_id?: number;
  area_code?: string;
  description: string;
  raised_by?: string;
  raised_date?: string;
  assigned_to?: string;
  target_date?: string;
  closeout_date?: string;
  closeout_verified_by?: string;
  status: string;
  priority?: string;
  discipline_name?: string;
  system_code?: string;
  system_name?: string;
}

// ── Commissioning ───────────────────────────────────────────────────
export interface CommissioningProcedure {
  procedure_id: string;
  sub_system_id: string;
  project_id: string;
  procedure_code: string;
  procedure_name?: string;
  procedure_type: string;
  description?: string;
  planned_date?: string;
  actual_date?: string;
  status: string;
  responsible_party?: string;
  witness_required: boolean;
  witness_party?: string;
  test_result?: string;
  system_code?: string;
  system_name?: string;
}

export interface CommissioningChecklistItem {
  checklist_id: string;
  procedure_id: string;
  item_number: number;
  check_description: string;
  expected_result?: string;
  actual_result?: string;
  is_verified: boolean;
  verified_by?: string;
  verified_date?: string;
  remarks?: string;
}

// ── Quality ─────────────────────────────────────────────────────────
export interface NCR {
  ncr_id: string;
  project_id: string;
  ncr_number: string;
  discipline_id?: number;
  sub_system_id?: string;
  activity_id?: string;
  severity: string;
  category?: string;
  description: string;
  immediate_action?: string;
  root_cause?: string;
  corrective_action?: string;
  preventive_action?: string;
  raised_by?: string;
  raised_date?: string;
  target_closeout_date?: string;
  actual_closeout_date?: string;
  verified_by?: string;
  status: string;
  discipline_name?: string;
  system_code?: string;
}

export interface WeldRecord {
  weld_id: string;
  project_id: string;
  weld_number: string;
  drawing_id?: string;
  discipline_id?: number;
  weld_type?: string;
  joint_type?: string;
  diameter_mm?: number;
  thickness_mm?: number;
  welder_id?: string;
  weld_date?: string;
  ndt_method?: string;
  ndt_result?: string;
  rejection_reason?: string;
  repair_count: number;
  status: string;
  discipline_name?: string;
  drawing_number?: string;
}

// ── Safety ──────────────────────────────────────────────────────────
export interface SafetyIncident {
  incident_id: string;
  project_id: string;
  incident_date: string;
  incident_time?: string;
  incident_type: string;
  severity: string;
  area_code?: string;
  discipline_id?: number;
  description: string;
  immediate_cause?: string;
  root_cause?: string;
  corrective_action?: string;
  preventive_action?: string;
  reported_by?: string;
  investigated_by?: string;
  lost_time_days: number;
  man_hours_at_incident?: number;
  status: string;
  discipline_name?: string;
}

export interface SafetyPermit {
  permit_id: string;
  project_id: string;
  permit_type: string;
  permit_number: string;
  work_description: string;
  area_code?: string;
  discipline_id?: number;
  requested_by?: string;
  approved_by?: string;
  issue_date?: string;
  expiry_date?: string;
  isolation_required?: string;
  gas_test_required?: string;
  gas_test_result?: string;
  status: string;
  days_to_expiry?: number;
  is_expired?: boolean;
  is_expiring_soon?: boolean;
}

export interface HSEStats {
  total_incidents: number;
  lti_count: number;
  recordable_count: number;
  fa_count: number;
  near_miss_count: number;
  total_lost_days: number;
  trir: number;
  ltifr: number;
  safe_man_hours: number;
}

// ── Training ────────────────────────────────────────────────────────
export interface TrainingRole {
  role_id: number;
  role_name: string;
  role_category?: string;
}

export interface TrainingCourse {
  course_id: number;
  course_code: string;
  course_name: string;
  course_category?: string;
  validity_months?: number;
  is_mandatory: boolean;
  description?: string;
}

export interface Personnel {
  personnel_id: string;
  project_id: string;
  badge_number?: string;
  full_name: string;
  role_id?: number;
  discipline?: string;
  contractor_company?: string;
  mobilization_date?: string;
  demobilization_date?: string;
  status: string;
  role_name?: string;
  role_category?: string;
}

export interface TrainingRecord {
  record_id: string;
  personnel_id: string;
  project_id: string;
  course_id: number;
  completion_date?: string;
  expiry_date?: string;
  certificate_ref?: string;
  score?: number;
  verified_by?: string;
  full_name?: string;
  badge_number?: string;
  course_code?: string;
  course_name?: string;
}

export interface TrainingMatrixCell {
  role_name: string;
  course_name: string;
  total_personnel: number;
  certified_count: number;
  compliance_pct: number;
}

export interface ExpiringCertification {
  full_name: string;
  badge_number?: string;
  discipline?: string;
  contractor_company?: string;
  course_name: string;
  certificate_ref?: string;
  expiry_date: string;
  days_remaining: number;
}

// ── Planning ────────────────────────────────────────────────────────
export interface PlanningPeriod {
  period_id: string;
  project_id: string;
  period_type: string;
  period_label?: string;
  period_start: string;
  period_end: string;
  is_locked: boolean;
  item_count?: number;
}

export interface PlanItem {
  plan_item_id: string;
  period_id: string;
  activity_id: string;
  planned_weight_pct?: number;
  actual_weight_pct?: number;
  milestone_flag: boolean;
  milestone_name?: string;
  status: string;
  variance_note?: string;
  activity_code?: string;
  activity_name?: string;
  is_critical?: boolean;
  work_scope_category?: string;
  current_progress?: number;
  period_start?: string;
  period_end?: string;
  period_type?: string;
}

// ── Conflicts ───────────────────────────────────────────────────────
export interface Conflict {
  conflict_id: string;
  project_id: string;
  conflict_type: string;
  title?: string;
  description?: string;
  source_entity_type?: string;
  source_entity_id?: string;
  target_entity_type?: string;
  target_entity_id?: string;
  severity: string;
  detected_by_agent: boolean;
  ai_confidence?: number;
  ai_recommendation?: string;
  status: string;
  resolution_notes?: string;
  resolved_by?: string;
  created_at?: string;
  resolved_at?: string;
  open_actions?: number;
}

// ── Feedback ────────────────────────────────────────────────────────
export interface FeedbackItem {
  feedback_id: string;
  project_id: string;
  source_stage: string;
  target_stage: string;
  feedback_type: string;
  reference_number?: string;
  description: string;
  impact_assessment?: string;
  impact_level: string;
  ai_generated_assessment: boolean;
  is_actioned: boolean;
  actioned_by?: string;
  actioned_date?: string;
  closure_notes?: string;
  created_by?: string;
  created_at?: string;
}

// ── Stage Gates ─────────────────────────────────────────────────────
export interface StageGate {
  gate_id: string;
  project_id: string;
  gate_name: string;
  gate_sequence: number;
  from_phase?: string;
  to_phase?: string;
  planned_date?: string;
  actual_date?: string;
  checklist_complete_pct: number;
  ai_readiness_score?: number;
  human_approver?: string;
  approval_date?: string;
  approver_comments?: string;
  status: string;
  total_checklist?: number;
  completed_checklist?: number;
}

export interface GateChecklistItem {
  checklist_item_id: string;
  gate_id: string;
  item_number: number;
  category?: string;
  description: string;
  verification_method?: string;
  is_complete: boolean;
  verified_by?: string;
  verified_date?: string;
  evidence_ref?: string;
  remarks?: string;
}

// ── Alerts ──────────────────────────────────────────────────────────
export interface ScheduleAlert {
  alert_id: string;
  project_id: string;
  alert_type: string;
  activity_id?: string;
  alert_title?: string;
  severity: string;
  recommended_action?: string;
  is_resolved: boolean;
}

// ── AI ──────────────────────────────────────────────────────────────
export interface AIStatus {
  enabled: boolean;
  model: string;
  features: string[];
}
