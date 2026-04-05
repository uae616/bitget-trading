import json, pathlib, re; 
p=pathlib.Path('state/futures_state.json'); 
acts=[]; 
if p.exists():
 d=json.loads(p.read_text(encoding='utf-8')); 
acts=d.get('activities',[]) if isinstance(d,dict) else []
opens=sum(1 for a in acts if str(a.get('action','')).startswith('OPEN_'))
closes=sum(1 for a in acts if str(a.get('action','')).startswith('CLOSE_'))
print(f'futures_open_actions={opens}')
print(f'futures_close_actions={closes}')
print(f'futures_total_activities={len(acts)}')
print(f'futures_last_activity={acts[-1] if acts else None}')"; if (Test-Path logs\futures_bot.log) { Write-Host 'futures_log_exists=True' } else { Write-Host 'futures_log_exists=False' }

