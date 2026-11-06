# Registers a Windows Task Scheduler job: every weekday at 07:30 (local PC time), user session, no password stored.
$bat = Join-Path $PSScriptRoot "run_daily.bat"
$action = New-ScheduledTaskAction -Execute $bat
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 7:30am
Register-ScheduledTask -TaskName "RiskReportDaily" -Action $action -Trigger $trigger -Force
