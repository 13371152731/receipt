"""Send one synthetic test message to an explicitly configured Feishu group."""
import argparse
import base64
import hashlib
import hmac
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
from urllib.parse import urlsplit

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--send',action='store_true',help='实际向配置的测试群发送一条消息')
    args=parser.parse_args()
    path=Path(__file__).resolve().parent/'data'/'feishu-test.local.json'
    config=json.loads(path.read_text(encoding='utf-8-sig'))
    url=config.get('webhook_url','').strip()
    target=urlsplit(url)
    if target.scheme!='https' or target.netloc!='open.feishu.cn' or not target.path.startswith('/open-apis/bot/v2/hook/') or not target.path.removeprefix('/open-apis/bot/v2/hook/') or target.query or target.fragment:
        raise ValueError('请填写飞书自定义机器人的完整 HTTPS Webhook 地址')
    group=config.get('test_group_name','').strip()
    if not group:raise ValueError('请填写测试群名称，确认发送目标')
    text='【证书预警 · 联通测试】\n以下为虚拟测试数据，不是实际人员通知。\n人员：测试人员甲\n项目：演示项目\n证书：低压电工作业证\n场景：模拟距到期还有 5 天\n请安全员核对续证或人员调整安排。'
    print('配置目标群：'+group+'（名称仅为本地备注）')
    print(text)
    if not args.send:
        print('预览完成，未发送。使用 --send 实际发送一条。');return
    payload={'msg_type':'text','content':{'text':text}}
    secret=config.get('signing_secret','').strip()
    if secret:
        timestamp=str(int(time.time()))
        signature=base64.b64encode(hmac.new((timestamp+'\n'+secret).encode(),b'',hashlib.sha256).digest()).decode()
        payload.update(timestamp=timestamp,sign=signature)
    request=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='POST')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=15) as response:result=json.load(response)
    except (urllib.error.URLError,TimeoutError):
        raise RuntimeError('网络请求失败或超时；请先查看群内是否收到，避免重复发送。') from None
    code=result.get('code',result.get('StatusCode'))
    if code!=0:raise RuntimeError('飞书未接受消息，错误码：'+str(code)+'；请检查机器人安全设置。')
    print('飞书接口已接受消息，请在测试群内确认实际显示。')

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError) as error:
        print(str(error));raise SystemExit(1)
