{{- define "aiwf.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "aiwf.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "aiwf.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "aiwf.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "aiwf.selectorLabels" -}}
app.kubernetes.io/name: {{ include "aiwf.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "aiwf.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "aiwf.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "aiwf.secretName" -}}
{{- default (printf "%s-secrets" (include "aiwf.fullname" .)) .Values.secrets.existingSecret -}}
{{- end -}}

{{- define "aiwf.backendImage" -}}
{{- if .Values.backend.image.digest -}}
{{- printf "%s@%s" .Values.backend.image.repository .Values.backend.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.backend.image.repository (default .Chart.AppVersion .Values.backend.image.tag) -}}
{{- end -}}
{{- end -}}

{{- define "aiwf.frontendImage" -}}
{{- if .Values.frontend.image.digest -}}
{{- printf "%s@%s" .Values.frontend.image.repository .Values.frontend.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.frontend.image.repository (default .Chart.AppVersion .Values.frontend.image.tag) -}}
{{- end -}}
{{- end -}}