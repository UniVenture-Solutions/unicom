# Planned stock shortage and expiry tasks

UniCom will turn stock validation findings into tasks that the responsible team can track from the dashboard. Each task stays active until a user closes it manually. An open task escalates to an issue after three days for further discussion.

## Task triggers

| Stock finding | Task created | Processing |
| --- | --- | --- |
| Stock shortage | Issue a Purchase Order | Record the Purchase Order against the task once it is issued. |
| Stock expiry | Process a stock return | Record the return document against the task once it is processed. |

## Task lifecycle

1. The system validates stock levels and expiry status. When it identifies a qualifying shortage or expiry, it creates the corresponding task automatically.
2. The user issues the Purchase Order or processes the return. The task remains active after the document has been issued or processed.
3. A user reviews the outcome and manually marks the task as completed or closed.
4. If the task is still open three days after creation, UniCom creates an issue for further discussion. The issue links to the original task and any Purchase Order or return already recorded. The task stays active until a user closes it.

## Implementation decisions

- Use a linked issue for escalation so the task keeps its history and manual closure. Create one escalation issue per task, even if the system checks it again.
- Confirm whether the three-day window uses calendar or business days.
- Confirm the shortage thresholds, expiry window, validation schedule, and rules for assigning tasks.
