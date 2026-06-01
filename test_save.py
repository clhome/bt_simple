import sys, os, json
sys.path.append('f:/git/gitea20250909/bt_simple/web')
sys.path.append('f:/git/gitea20250909/bt_simple/plugins/op_star')
import core.mw as mw
import index

index.getArgs = lambda: {'rule_name': 'ip_Mod', 'rule_data': json.dumps([["172.17.60.218", "deny", "test"]])}
res = index.save_rule()
print('RESULT:', res)

with open(index.getServerDir() + '/conf_json/ip/deny.ip', 'r') as f:
    print('DENY IP CONTENT: ' + repr(f.read()))
