/** Shared status constants — mirrors backend/constants.py */

export const DrawingStatus = {
  WIP: 'WIP',
  IFA: 'IFA',
  IFC: 'IFC',
  AFC: 'AFC',
  REVISED: 'REVISED',
  CANCELLED: 'CANCELLED',
} as const;
export type DrawingStatus = (typeof DrawingStatus)[keyof typeof DrawingStatus];

export const MVRStatus = {
  INFO_AFI: 'Info-AFI',
  STRUCTURE_REQUESTED: 'Structure-requested',
  PIPING_REQUESTED: 'piping-requested',
  MVR_CONFIRM: 'MVR-confirm',
  CANCELLED: 'CANCELLED',
} as const;
export type MVRStatus = (typeof MVRStatus)[keyof typeof MVRStatus];

export const POStatus = {
  ORDERED: 'ORDERED',
  PR_RAISED: 'PR-RAISED',
  PARTIALLY_RECEIVED: 'PARTIALLY_RECEIVED',
  RECEIVED: 'RECEIVED',
  CANCELLED: 'CANCELLED',
} as const;
export type POStatus = (typeof POStatus)[keyof typeof POStatus];

export const CompletionStatus = {
  NOT_STARTED: 'NOT_STARTED',
  IN_PROGRESS: 'IN_PROGRESS',
  READY_FOR_MC: 'READY_FOR_MC',
  MC_COMPLETE: 'MC_COMPLETE',
  HANDED_OVER: 'HANDED_OVER',
} as const;
export type CompletionStatus = (typeof CompletionStatus)[keyof typeof CompletionStatus];

export const NCRSeverity = {
  CRITICAL: 'CRITICAL',
  MAJOR: 'MAJOR',
  MINOR: 'MINOR',
  OBSERVATION: 'OBSERVATION',
} as const;
export type NCRSeverity = (typeof NCRSeverity)[keyof typeof NCRSeverity];

export const IncidentType = {
  LTI: 'LTI',
  MTI: 'MTI',
  RWC: 'RWC',
  FA: 'FA',
  NEAR_MISS: 'NEAR_MISS',
  OBSERVATION: 'OBSERVATION',
  FIRST_AID: 'FIRST_AID',
} as const;
export type IncidentType = (typeof IncidentType)[keyof typeof IncidentType];

export const StageGateStatus = {
  PENDING: 'PENDING',
  IN_REVIEW: 'IN_REVIEW',
  APPROVED: 'APPROVED',
  REJECTED: 'REJECTED',
  CONDITIONAL: 'CONDITIONAL',
} as const;
export type StageGateStatus = (typeof StageGateStatus)[keyof typeof StageGateStatus];

export const ConflictStatus = {
  DETECTED: 'DETECTED',
  ACKNOWLEDGED: 'ACKNOWLEDGED',
  IN_RESOLUTION: 'IN_RESOLUTION',
  RESOLVED: 'RESOLVED',
  CLOSED: 'CLOSED',
} as const;
export type ConflictStatus = (typeof ConflictStatus)[keyof typeof ConflictStatus];

export const PlanItemStatus = {
  ON_TRACK: 'ON_TRACK',
  AT_RISK: 'AT_RISK',
  DELAYED: 'DELAYED',
  COMPLETED: 'COMPLETED',
} as const;
export type PlanItemStatus = (typeof PlanItemStatus)[keyof typeof PlanItemStatus];

export const PermitStatus = {
  REQUESTED: 'REQUESTED',
  APPROVED: 'APPROVED',
  ISSUED: 'ISSUED',
  SUSPENDED: 'SUSPENDED',
  CLOSED: 'CLOSED',
  CANCELLED: 'CANCELLED',
} as const;
export type PermitStatus = (typeof PermitStatus)[keyof typeof PermitStatus];
