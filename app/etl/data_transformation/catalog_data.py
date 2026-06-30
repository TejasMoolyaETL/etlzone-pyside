"""Sample transformation catalog (Object → Job → Flow → Work Flow)."""

from __future__ import annotations

from typing import Any

SAMPLE_OBJECTS: list[dict[str, Any]] = [
    {
        "objectName": "Customer Master",
        "objectCode": "CM",
        "description": "SAP customer master data (KNA1, KNVV, …)",
        "status": "Active",
    },
    {
        "objectName": "Material Master",
        "objectCode": "MM",
        "description": "SAP material master data (MARA, MARC, …)",
        "status": "Active",
    },
]

SAMPLE_JOBS: list[dict[str, Any]] = [
    {
        "jobName": "CM_Preload",
        "objectName": "Customer Master",
        "jobType": "Preload",
        "description": "Stage and prepare customer master source tables",
        "status": "Active",
    },
    {
        "jobName": "CM_Load",
        "objectName": "Customer Master",
        "jobType": "Load",
        "description": "Load validated customer master into target",
        "status": "Active",
    },
    {
        "jobName": "MM_Preload",
        "objectName": "Material Master",
        "jobType": "Preload",
        "description": "Stage material master source tables",
        "status": "Draft",
    },
    {
        "jobName": "MM_Load",
        "objectName": "Material Master",
        "jobType": "Load",
        "description": "Load material master into target",
        "status": "Draft",
    },
]

SAMPLE_FLOWS: list[dict[str, Any]] = [
    {
        "flowName": "F1_CM_KNA1_Relevancy",
        "jobName": "CM_Preload",
        "flowType": "Relevancy",
        "sourceTable": "KNA1",
        "description": "Filter relevant customer general data",
        "status": "Active",
    },
    {
        "flowName": "F2_CM_KNA1_Map",
        "jobName": "CM_Preload",
        "flowType": "Map",
        "sourceTable": "KNA1",
        "description": "Map KNA1 fields to staging layout",
        "status": "Active",
    },
    {
        "flowName": "F3_CM_KNA1_Validation",
        "jobName": "CM_Load",
        "flowType": "Validation",
        "sourceTable": "KNA1",
        "description": "Validate customer general data rules",
        "status": "Active",
    },
    {
        "flowName": "F4_CM_KNA1_Enrich",
        "jobName": "CM_Load",
        "flowType": "Enrich",
        "sourceTable": "KNA1",
        "description": "Enrich customer records with derived attributes",
        "status": "Active",
    },
    {
        "flowName": "F5_CM_KNVV_Relevancy",
        "jobName": "CM_Preload",
        "flowType": "Relevancy",
        "sourceTable": "KNVV",
        "description": "Filter relevant sales-area customer data",
        "status": "Active",
    },
    {
        "flowName": "F6_MM_MARA_Map",
        "jobName": "MM_Preload",
        "flowType": "Map",
        "sourceTable": "MARA",
        "description": "Map material general data",
        "status": "Draft",
    },
]

SAMPLE_WORKFLOWS: list[dict[str, Any]] = [
    {
        "workflowName": "WF_CM_KNA1_Pipeline",
        "jobName": "CM_Load",
        "flowSequence": (
            "F1_CM_KNA1_Relevancy → F2_CM_KNA1_Map → "
            "F3_CM_KNA1_Validation → F4_CM_KNA1_Enrich"
        ),
        "description": "End-to-end KNA1 customer master pipeline",
        "status": "Active",
    },
    {
        "workflowName": "WF_CM_Multi_Table_Relevancy",
        "jobName": "CM_Preload",
        "flowSequence": "F1_CM_KNA1_Relevancy, F5_CM_KNVV_Relevancy",
        "description": "Parallel relevancy for KNA1 and KNVV",
        "status": "Active",
    },
    {
        "workflowName": "WF_MM_MARA_Staging",
        "jobName": "MM_Preload",
        "flowSequence": "F6_MM_MARA_Map",
        "description": "Material master staging workflow",
        "status": "Draft",
    },
]
