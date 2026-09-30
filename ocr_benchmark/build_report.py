from pathlib import Path
import csv
import json
import statistics
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / 'outputs'
QA = ROOT / 'report_qa'
OUT.mkdir(exist_ok=True)
QA.mkdir(exist_ok=True)
PROFILES = ['gpu_full','gpu_standard','gpu_960']
S = {p:json.loads((ROOT/p/'summary.json').read_text(encoding='utf-8')) for p in PROFILES}
M = {p:json.loads((ROOT/p/'metadata.json').read_text(encoding='utf-8')) for p in PROFILES+['cpu_standard']}
samples = M['gpu_standard']['samples']

# Numeric results are derived from saved measurements, never retyped.
with (OUT/'PaddleOCR实测速率.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w = csv.writer(f)
    w.writerow(['配置','样本','文件名','图宽','图高','第1轮秒','第2轮秒','第3轮秒','平均秒','本地读取解码中位数秒'])
    for p in PROFILES:
        for sample in samples:
            v = S[p]['by_image'][sample['id']]
            w.writerow([p,sample['id'],sample['filename'],sample['width'],sample['height'],*[round(x,6) for x in v['values_s']],round(v['mean_s'],6),round(sample['read_decode_median_s'],6)])

def font(size, bold=False):
    return ImageFont.truetype(r'C:\Windows\Fonts\msyhbd.ttc' if bold else r'C:\Windows\Fonts\msyh.ttc',size)

# A compact system diagram with no certificate photos or personal identifiers.
im = Image.new('RGB',(1500,640),'white')
d = ImageDraw.Draw(im)
boxes = [(460,20,1040,115,'管理网页与安全员手机端'),(460,190,1040,305,'业务 API 与规则引擎'),(20,395,460,535,'OCR 任务与常驻 GPU'),(530,395,970,535,'数据库与证书附件'),(1040,395,1480,535,'预警任务与通知渠道')]
for x1,y1,x2,y2,label in boxes:
    d.rounded_rectangle((x1,y1,x2,y2),radius=15,fill='#F4F6F8',outline='#6E7A86',width=3)
    b=d.textbbox((0,0),label,font=font(30,True)); d.text(((x1+x2-b[2])/2,(y1+y2-b[3])/2),label,font=font(30,True),fill='black')
def arrow(points):
    d.line(points,fill='#34495E',width=4)
    x,y=points[-1]; d.polygon([(x,y),(x-9,y-16),(x+9,y-16)],fill='#34495E')
arrow([(750,115),(750,190)])
arrow([(750,305),(750,350),(240,350),(240,395)])
arrow([(750,305),(750,395)])
arrow([(750,305),(750,350),(1260,350),(1260,395)])
d.text((227,572),'提取文字与坐标',font=font(25),fill='#555555')
d.text((623,572),'审核后形成台账',font=font(25),fill='#555555')
d.text((1115,572),'提醒与处理跟踪',font=font(25),fill='#555555')
diagram = QA/'architecture.png'; im.save(diagram)

doc = Document()
sec=doc.sections[0]
sec.page_width=Cm(21); sec.page_height=Cm(29.7)
sec.top_margin=Cm(1.85); sec.bottom_margin=Cm(1.8)
sec.left_margin=Cm(2); sec.right_margin=Cm(2)
sec.header_distance=Cm(.7); sec.footer_distance=Cm(.8)
for name in ['Normal','Title','Subtitle','Heading 1','Heading 2','Heading 3','Caption']:
    st=doc.styles[name]; st.font.name='Arial'; st.font.color.rgb=RGBColor(0,0,0)
    st.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'微软雅黑')
for border in doc.styles.element.xpath('.//w:pBdr'):
    border.getparent().remove(border)
doc.styles['Title'].font.underline=False
doc.styles['Subtitle'].font.italic=False
normal=doc.styles['Normal']; normal.font.size=Pt(10.5)
normal.paragraph_format.line_spacing=1.22
normal.paragraph_format.space_after=Pt(6)
for name,size in [('Title',22),('Subtitle',12),('Heading 1',16),('Heading 2',11.5)]:
    st=doc.styles[name]; st.font.size=Pt(size)
    st.paragraph_format.space_before=Pt(10 if name.startswith('Heading') else 0)
    st.paragraph_format.space_after=Pt(7)
    st.paragraph_format.keep_with_next=True
    if name.startswith('Heading'): st.font.bold=True
doc.styles['Caption'].font.size=Pt(9)
doc.core_properties.title='工地人员证书预警与替补推荐系统技术报告'
doc.core_properties.subject='本地 PaddleOCR 实测速率与系统实施方案'
doc.core_properties.author=''
doc.core_properties.keywords='PaddleOCR 证书 到期提醒 人员调配 性能测试'
footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
footer.add_run('第 ').font.size=Pt(9)
field=OxmlElement('w:fldSimple'); field.set(qn('w:instr'),'PAGE'); footer._p.append(field)
footer.add_run(' 页').font.size=Pt(9)

def p(text='',bold=False):
    para=doc.add_paragraph(); run=para.add_run(text); run.bold=bold
    return para
def h(text,level=2): return doc.add_paragraph(text,f'Heading {level}')
def page(title):
    para=h(title,1); para.paragraph_format.page_break_before=True
def table(headers,rows,widths):
    t=doc.add_table(rows=1,cols=len(headers)); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.autofit=False
    pr=t._tbl.tblPr
    borders=OxmlElement('w:tblBorders')
    for side in ['top','left','bottom','right','insideH','insideV']:
        el=OxmlElement('w:'+side); el.set(qn('w:val'),'single'); el.set(qn('w:sz'),'4'); el.set(qn('w:color'),'D9D9D9'); borders.append(el)
    pr.append(borders)
    for row in [headers]+rows:
        cells=t.rows[0].cells if row is headers else t.add_row().cells
        row_idx=0 if row is headers else len(t.rows)-1
        trpr=cells[0]._tc.getparent().get_or_add_trPr()
        nosplit=OxmlElement('w:cantSplit'); trpr.append(nosplit)
        if row_idx==0:
            rep=OxmlElement('w:tblHeader'); trpr.append(rep)
        for i,(cell,text) in enumerate(zip(cells,row)):
            cell.width=Cm(widths[i]); cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr=cell._tc.get_or_add_tcPr(); mar=OxmlElement('w:tcMar')
            for side,val in [('top',85),('bottom',85),('left',95),('right',95)]:
                e=OxmlElement('w:'+side); e.set(qn('w:w'),str(val)); e.set(qn('w:type'),'dxa'); mar.append(e)
            tcpr.append(mar)
            shade=OxmlElement('w:shd'); shade.set(qn('w:fill'),'24425C' if row_idx==0 else ('F2F5F7' if row_idx%2==0 else 'FFFFFF')); tcpr.append(shade)
            para=cell.paragraphs[0]; para.paragraph_format.space_after=Pt(0); para.paragraph_format.line_spacing=1.12
            if len(str(text))<16: para.alignment=WD_ALIGN_PARAGRAPH.CENTER
            run=para.add_run(str(text)); run.font.size=Pt(9.2); run.bold=row_idx==0
            if row_idx==0: run.font.color.rgb=RGBColor(255,255,255)
    for i,width in enumerate(widths): t.columns[i].width=Cm(width)
    spacer=doc.add_paragraph()
    spacer.paragraph_format.space_after=Pt(3)
    spacer.paragraph_format.line_spacing=Pt(2)
    spacer.add_run('').font.size=Pt(2)
    return t

doc.add_paragraph('工地人员证书预警与替补推荐系统', 'Title')
doc.add_paragraph('技术报告与本地 PaddleOCR 性能测试', 'Subtitle')
p('报告日期  2026 年 9 月 7 日    版本  1.0')
h('1 主要结论',1)
p('建议采用本地 PaddleOCR 提取证书文字，由业务规则与人工审核确认关键字段，再驱动到期预警、项目缺岗预测和替补推荐。系统以人员、证书、岗位需求、项目排班和在场状态为核心数据，形成从上传到处理完成的可追溯流程。')
p(f'在现有 RTX 4060 Laptop 8GB 电脑上，关闭 UVDoc 图像矫正并保留方向识别的配置，常驻模型平均耗时 {S["gpu_standard"]["mean_s"]:.3f} 秒每张，9 张截图一轮平均 {S["gpu_standard"]["mean_nine_image_pass_s"]:.2f} 秒。该速度来自真实本地推理，不含上传、排队、字段审核和消息推送。')
table(['本次验证内容','结论'],[
    ['GPU 常驻识别速度','平均 0.318 秒每张，P95 为 0.552 秒'],
    ['有效期止文本提取','最快配置在 7 张截图中命中，共 9 张'],
    ['缺失字段','T01 与 T04 的到期日期漏读，二者为同证近重复图'],
    ['上线建议','OCR 结果先进入审核队列，缺失日期不得自动判为有效'],
],[4,13])
h('建设范围与业务收益')
p('第一期覆盖证书上传与台账、关键字段确认、到期和复审提醒、项目用工缺口预测、候选人推荐、负责人确认与操作留痕。提前 10 天和 5 天提醒安全员，并允许按项目配置；到期未处理或在场状态异常时升级提醒。')
p('推荐人员必须满足岗位所需的证书类型和等级，证书与复审记录覆盖拟派工期间，排班无冲突且允许调配。系统输出候选名单与推荐原因，由负责人确认后形成实际派工记录。')
h('本次验证边界')
p('本次完成 OCR 本地性能测试和关键日期文本核查，未实施生产业务系统、门禁联动或通知平台发送。9 张截图含重复证书和近重复图片，不能据此推断全量证书准确率或长期服务吞吐。原始 OCR 输出与逐轮记录已保存在本地测试目录。')

page('2 业务流程与关键判断规则')
h('从证书上传到风险解除')
p('上传证书后先生成识别任务，返回识别文字、位置与置信度。工作人员对照原图确认姓名、证书号、作业项目、有效期和复审信息。审核通过后形成新版本台账，并立即检查该人员当前及未来项目安排。续证时保留旧版本，重新计算提醒任务和缺岗预测。')
table(['节点','系统动作','处理责任'],[
    ['提前 10 天','提醒临期风险，同时预测岗位缺口','安全员确认续证或换人'],
    ['提前 5 天','更新风险与候选人，催办未完成任务','安全员与项目负责人'],
    ['提前 1 天','可选加急提醒，检查替补到岗安排','项目负责人'],
    ['到期及以后','持续跟踪未解决风险，按规则升级','负责人确认现场处置'],
    ['续证或换人完成','审核材料并确认排班或进退场，再关闭任务','审核员与项目负责人'],
],[2.4,8.4,6.2])
h('有效期与复审必须分别管理')
p('证书有效期、应复审日期和复审通过记录是不同字段。例如 T09 图片写有有效期至 2029 年 2 月 16 日，同时写有应于 2026 年 2 月 16 日前复审。以报告日期看，后一个时间点已过去，但仅凭截图不能确认是否已完成复审，系统应标记“复审情况待核实”。')
p('旧证中“复审日期”可能只写到年月，也可能包含历史记录；不可直接当成下一次复审截止日。保留原文、日期精度和字段语义，无法确定时转人工确认。不得将缺失日期补成任意日期，也不得按固定年限猜测。')
h('岗位缺口按未来时间计算')
p('按项目、岗位和时间段比较需求人数与符合条件的可用人数。例如某岗位需 3 人，其中 1 人将在 5 天后失去已确认的资质覆盖，则形成 5 天后的潜在缺口。只有确认续证通过、替补可用或需求变更后，才消除相应缺口。')
h('在场状态需要可靠来源')
p('接入考勤或门禁后，可对“已失效或待核实资质人员仍在场”触发告警。第一期没有接口时，由项目维护进退场名单并显示更新时间。状态过旧、退出未确认或接口中断时，要提示数据待核实。只有消息提醒不能证明现场风险已解除。')

page('3 系统架构与数据设计')
p('采用模块化单体作为业务后台，并将 OCR 作为独立常驻工作进程运行。浏览器提交任务后立即获得任务编号，前端通过查询或事件通知获取结果。数据库保存任务状态，避免识别请求长时间占住网页连接。')
pic=doc.add_paragraph(); pic.alignment=WD_ALIGN_PARAGRAPH.CENTER
pic.add_run().add_picture(str(diagram),width=Cm(16.8))
for shape in doc.inline_shapes:
    shape._inline.docPr.set('descr','系统由管理端、业务 API、OCR 工作进程、数据库与附件、预警通知模块组成')
table(['模块','建议选型','主要职责'],[
    ['管理界面','Vue 3 响应式网页','台账、审核、安全员手机处理与风险看板'],
    ['业务后台','Python FastAPI','权限、规则、岗位需求、匹配和审批'],
    ['数据层','PostgreSQL 与附件存储','业务关系、原图、证书版本和任务记录'],
    ['后台任务','Celery 与 Redis','OCR 队列、定期扫描和失败重试'],
    ['OCR 推理','本地 PaddleOCR 与 GPU','模型常驻，输出文字、坐标和置信度'],
],[2.4,5,9.6])
h('核心数据对象')
p('人员表记录工种、技能和所属单位；证书表与证书版本表保存有效期、复审信息、审核状态和原图位置；岗位要求表保存所需资质组合；项目排班表记录使用起止时间；进退场记录表保存实际状态和数据来源；预警任务、通知记录和调配申请分别保留处理过程。')
h('架构选择与取舍')
p('决定一：业务采用模块化单体，以较低运维成本实现一致的审核与调配流程；未来按规模拆分。决定二：OCR 采用常驻异步进程，避免每张图片重复加载模型，代价是需要维护任务队列和工作进程健康检查。决定三：资格判断采用明确规则，推荐排序可解释，减少关键日期和资质被错误推断的风险。')

page('4 OCR 提取与关键字段审核方案')
h('识别流程')
p('原图上传与校验 → 文档方向识别 → 文本检测 → 文本行方向识别 → 文字识别 → 证书类型与字段解析 → 规则校验 → 人工确认 → 台账生效。采用本地模型完成图像识别；第一期关键字段解析使用字段标签、文字坐标、日期格式和证书类型规则。')
p('OCR 自带的置信度是文字识别分数，不能直接作为证书真实有效的概率。保留原文和坐标，让审核人员点击字段即可定位对应图片区域。截图中的 WPS 弹窗、页面标题和“有效证书数量”属于页面内容，不应直接写成该证书当前审核结论。')
table(['字段','处理方式','必须拦截的情况'],[
    ['证书类型和作业项目','使用受控字典与原文位置关联','低压与高压混淆，字段漏读'],
    ['人员姓名和证书编号','与人员档案核对，保留原文','人员不匹配，编号冲突'],
    ['有效期开始与结束','解析起止语义并校验日期','结束早于开始，关键日期缺失'],
    ['复审信息','区分历史记录与下次截止时间','语义不明，只有年月或多个冲突日期'],
    ['英文有效期','解析 Valid Through 与英文月份','月份无法解析，多个候选日期'],
    ['证书更新与重复上传','文件哈希与人员证书版本关联','旧版本覆盖新版本，重复提醒'],
],[3.3,6.7,7])
h('针对样本的处理策略')
p('倒置图片保留方向识别模块。带大面积空白、弹窗或多证书的页面，后续增加证书区域定位与必要的局部重识别。旧版水印证书的日期漏读应进入人工复核，重识别仍缺失时要求更清晰材料。区域定位与自动重识别属于后续实施内容，本次未计入性能指标。')
h('为什么不默认开启所有预处理')
p('本次开启 UVDoc 后平均耗时增加，且有效期止文本命中由 7 张降为 5 张；不能假设增加图像矫正就一定提高此类截图的效果。长边 960 配置和降低检测阈值的补充试验也未补齐两张旧证日期。第一期建议使用较快配置作为基础，将失败识别交给有针对性的补救与审核。')

page('5 测试环境与计时方法')
table(['项目','本次实际环境'],[
    ['操作系统','Windows 11 版本 10.0.26200'],
    ['处理器与内存','Intel Core i9-13900HX，32 逻辑处理器，约 15.73 GiB 可识别物理内存'],
    ['显卡','NVIDIA GeForce RTX 4060 Laptop GPU，8188 MiB，驱动 560.94'],
    ['解释器','现有 D:\\python1\\python.exe，Python 3.13.4'],
    ['框架版本','PaddleOCR 3.3.2，PaddlePaddle 3.2.2 CUDA 构建，PaddleX 3.3.12'],
    ['主要模型','PP-OCRv5_server_det 与 PP-OCRv5_server_rec'],
    ['方向模型','PP-LCNet_x1_0_doc_ori 与 PP-LCNet_x1_0_textline_ori'],
    ['推理设置','单进程单请求；文本识别批大小 6；FP32；未启用 TensorRT 或 HPI'],
],[3.3,13.7])
h('样本与重复次数')
p('使用提供的 9 张原始 PNG 截图，分辨率为 1036 至 1636 像素宽、573 至 1308 像素高。包含倒置、留白、斜拍、水印、英文和弹窗遮挡。T01 与 T04 为同证近重复图，T02 与 T05 为同证不同方向截图，因此不是 9 张独立证书。每个成功的 GPU 配置先测首次推理，再对全部图片预热一轮，最后以固定随机顺序运行 3 轮，共 27 次正式测量。')
h('计时口径')
p('OCR 计时从已解码图像传入 predict 开始，到全部结果实际生成并完成 GPU 同步结束，包含方向处理、检测、识别及后处理。文件读取解码另测 3 次取中位数，不混入 OCR 时间。模型导入、模型初始化和首次推理分别计时。没有把创建惰性迭代器的时间当成完整识别时间。')
p('平均值为 27 次耗时的算术平均；P95 用线性插值计算；串行吞吐按测量次数除以总识别时间换算。每张图片均有 3 个正式计时。桌面环境未做系统缓存清空或持续负载隔离，P95 和吞吐仅反映这次小样本测试，不构成生产服务承诺。')
h('本地环境处理')
p('原环境存在可选 Torch CUDA 库冲突，测试进程临时禁用无关 Torch 导入；识别权重原位于缓存临时目录，复制到测试模型目录后成功加载。因 Paddle 原生库对中文模型路径报错，模型副本改放在可写的纯英文路径。没有升级或重装现有环境，图片未上传外部识别服务。模型复制与排障耗时不计入推理速度。')

page('6 GPU 实测速率与启动开销')
p('三组均使用相同检测识别模型和方向识别模块。A 开启 UVDoc，B 关闭 UVDoc；二者检测尺寸采用本地默认 min 64。C 在 B 基础上改为检测长边最大 960。其余配置及完整参数保存在对应 pipeline.yaml 和 metadata.json。')
table(['配置','平均秒每张','P95 秒','9 张一轮秒','换算张每分钟'],[
    [label,f'{S[pr]["mean_s"]:.3f}',f'{S[pr]["p95_s"]:.3f}',f'{S[pr]["mean_nine_image_pass_s"]:.2f}',f'{S[pr]["serial_images_per_minute"]:.1f}']
    for label,pr in [('A 开启矫正','gpu_full'),('B 关闭矫正','gpu_standard'),('C 长边 960','gpu_960')]
],[3.4,3.2,2.5,3.5,4.4])
h('每张原始截图的常驻识别耗时')
table(['样本','文件尾号','分辨率','A 秒','B 秒','C 秒'],[
    [v['id'],v['filename'].split()[-1].replace('.png',''),f'{v["width"]} × {v["height"]}',*[f'{S[pr]["by_image"][v["id"]]["mean_s"]:.3f}' for pr in PROFILES]] for v in samples
],[1.4,2.8,4.4,2.8,2.8,2.8])
h('进程启动与首次推理')
table(['配置','导入秒','模型加载秒','首次 OCR 秒','进入脚本至首结果秒'],[
    [label,f'{M[pr]["import_s"]:.2f}',f'{M[pr]["model_initialization_s"]:.2f}',f'{M[pr]["first_inference_s"]:.2f}',f'{M[pr]["process_entry_to_first_result_s"]:.2f}']
    for label,pr in [('A','gpu_full'),('B','gpu_standard'),('C','gpu_960')]
],[1.6,2.6,3.5,3.5,5.8])
p('首次 OCR 固定使用 T01，各阶段各记录一次；“进入脚本至首结果”还含样本读取和环境信息采集，不含操作系统创建进程的时间。C 组启动较慢，单次观测不足以判断是否由参数变化造成。生产系统应常驻模型并在启动后预热。')
p(f'B 组本地读取与解码的各图中位数为 {min(v["read_decode_median_s"] for v in samples)*1000:.1f} 至 {max(v["read_decode_median_s"] for v in samples)*1000:.1f} 毫秒，未包含网络上传。上述“张每分钟”是串行推理换算值，未做持续一分钟或并发压测。')

page('7 关键日期核查与 CPU 探测结果')
p('下表以原图人工阅读的有效期止日期作为参考，核查 B 组第一轮原始 OCR 文本是否出现相同日期。仅统一空格、分隔符和英文月份；不是端到端字段抽取准确率，不代表其他字段正确，也不代表证书当前真实有效。')
quality=[
    ['T01','2025-03-18','未命中','有效期和复审日期漏读'],
    ['T02','2019-03-18','命中','复审只含年月 2016-03'],
    ['T03','2025-07-18','命中','起始日期分隔异常，复审行漏读'],
    ['T04','2025-03-18','未命中','与 T01 同证，关键日期同样漏读'],
    ['T05','2019-03-18','命中','倒置图纠正成功，准操项目仍漏读'],
    ['T06','2027-01-31','命中','另读出应复审日期 2024-01-31'],
    ['T07','2026-05-25','命中','原文为 May 25,2026，含弹窗噪声'],
    ['T08','2029-12-05','命中','另读出应复审日期 2026-12-05'],
    ['T09','2029-02-16','命中','另读出应复审日期 2026-02-16'],
]
table(['样本','人工参考日期','B 组结果','其他发现'],quality,[1.4,3.5,2.5,9.6])
p('有效期止文本命中情况：A 组 5 张，B 组 7 张，C 组 7 张，分母均为 9 张截图。B 组两张失败图片属于同一证书；不得把这个小样本比例写成面向全部证书的模型准确率。降低检测阈值的 6 次诊断调用也没有补齐该证书日期，未纳入正式速度统计。')
h('CPU 仅完成单图探测')
cpu=M['cpu_standard']
p(f'在同一现有 Paddle CUDA 构建中显式指定 CPU、8 线程并开启 MKL-DNN：T01 首次推理 {cpu["first_inference_s"]:.2f} 秒，再次推理 18.56 秒。后续图片未在短时间内返回，已主动停止该进程，未完成整组测试。因此没有 CPU 的九图平均值、P95 或吞吐指标，也不将这两个数字与 GPU 九图均值计算加速倍数。')
h('对上线方案的影响')
p('现有电脑可以提供较快的 GPU OCR 响应，但当前配置仍需人工核对日期与岗位资质。建议 GPU 部署先进入小范围试用；若客户必须使用 CPU，应在独立 CPU 环境和目标服务器上重新测量，并评估较轻模型。不能用本次未完成的 CPU 探测结果替代完整选型。')

page('8 预警可靠性与替补推荐实现')
h('通知必须能追踪处理结果')
p('按证书版本、提醒类型、阈值和接收人生成唯一任务键，防止同一节点重复提醒。定时扫描按“当前已进入预警区间且尚未完成处理”查询，停机恢复后补查遗漏任务，而非只在某个日期精确相等时触发。证书续期通过后取消旧版本尚未发送的提醒。')
p('通知任务区分待发送、发送成功、失败重试、人工确认和处理完成。发送成功只说明渠道接收请求；超过约定时间未确认时升级给项目负责人。安全员变更、无接收人、接口失败和连续任务失败进入异常清单。企业微信、钉钉或飞书优先对接客户已有平台，具体发送能力取决于客户应用配置。')
h('先检查资格再排序候选人')
table(['判断阶段','规则或动作'],[
    ['硬条件筛选','岗位要求的全部资质满足；审核通过；有效期与复审覆盖安排期间；排班不冲突；允许调配'],
    ['可用性确认','结合人员所属单位、当前项目释放时间、到岗时间和地域条件'],
    ['候选排序','按到岗时间、距离、同类项目经验、调配成本等客户认可因素排序'],
    ['推荐解释','展示每项满足依据、证书覆盖时间、可到岗时间和待确认事项'],
    ['调配提交','事务内再次检查排班和资格，负责人确认后更新占用，防止重复派工'],
    ['无合格候选人','明确显示缺口和缺少条件，转人工协调；不放宽必须资质条件'],
],[3.5,13.5])
h('权限与数据留存')
p('按公司、项目和角色隔离访问。安全员查看其负责项目，审核员处理证书材料，负责人确认调配。敏感编号默认脱敏展示，原图采用受控访问地址；识别结果、人工修改前后值、修改原因和审核人均留痕。对数据库、附件和任务状态做备份，并监控 OCR 队列长度、失败率、超时和 GPU 工作进程健康。')
h('门禁联动属于独立集成')
p('“已到期且仍在场”告警依赖进退场数据的完整性。若进一步联动门禁，需要确认现场处置流程、设备接口、异常恢复和人工通行处理，单独验收。当前技术方案不以证书照片或单条 OCR 结果自动改变现场通行权限。')

page('9 实施步骤与验收建议')
table(['阶段','交付内容','验收重点'],[
    ['数据准备','整理证书类型、岗位资质矩阵、人员和项目基础台账','明确有效期与复审语义，建立人工标注集'],
    ['OCR 与审核','上传、后台识别、字段定位、人工确认、版本管理','漏读可追踪，缺失字段被拦截，旧证不覆盖新证'],
    ['预警与闭环','10 天与 5 天规则、消息适配、确认催办、异常清单','停机补查、失败重试、去重和续证取消旧提醒'],
    ['人员推荐','缺岗预测、资格筛选、候选解释和调配确认','全资质覆盖、时间不冲突、并发提交不重复占用'],
    ['现场试用','接入实际项目与受控通知账号，观察反馈','完成全流程演练并校正数据维护责任'],
],[2.6,7.2,7.2])
h('建议明确的验收条件')
p('OCR 验收分别统计姓名、证书号、作业项目、有效期止和应复审日期的正确率、漏读率及人工审核比例；按不同证书和版式去重后分层评估，近重复图片归入同一组。阈值调试集与验收集分开。建议扩展至至少 200 张有人工标注的独立证书样本，再确定自动入库范围。')
p('速度验收在客户目标硬件上进行，分别测单请求 P50 和 P95、持续吞吐、并发排队、失败重试及完整上传到返回耗时。可将本次 GPU 常驻平均约 0.32 秒作为试用基线；重识别、区域裁切、上传和排队的额外耗时需另行测试后设定服务目标。')
p('业务验收覆盖临期、已到期、复审信息缺失、通知无人确认、证书更新、离场未同步、无候选人和两人同时调配同一候选人等场景。消息发送成功不得自动关闭风险任务；未确认的日期和证书状态不得参与“合格替补”的判断。')
h('启动实施前需落实的数据与接口')
p('客户需提供人员与项目规模、每日新增证书量和峰值上传量、证书类别与岗位要求、证书审核责任人、安全员及升级接收人、现有通知平台和进退场数据来源。还需明确跨项目调配审批方式、数据部署位置、原图保存期限和目标服务器配置。以上条件决定容量、接口范围和实施排期。')
h('部署建议')
p('业务服务、数据库和 OCR 进程可先部署在一台满足试用要求的服务器上，按队列隔离 OCR 工作；生产环境再结合可靠性和数据量配置独立数据库备份及备用恢复方案。锁定实际验证过的框架、模型版本和模型校验值，避免开发机的可选依赖冲突进入生产。')

page('10 测试复现与技术参考')
h('本地测试产物')
p('当前项目的 ocr_benchmark 目录保留测速脚本、原始文字与坐标、逐轮耗时、配置和模型清单。原始结果含证书个人信息，应按证书台账权限保存。报告正文用 T01 至 T09 标识图片，不重复展示完整人员编号。')
table(['文件或目录','用途'],[
    ['benchmark.py','GPU 三组与 CPU 探测的计时脚本'],
    ['gpu_full 与 gpu_standard 与 gpu_960','成功 GPU 测试的 summary.json、measurements.json、metadata.json、pipeline.yaml 和 ocr_results.json'],
    ['cpu_standard','CPU 的环境元数据和部分事件，整组已停止，无汇总结果'],
    ['models/manifest.json','本地模型源文件、哈希和临时目录权重来源记录'],
    ['detection_trials.json','降低阈值的诊断输出，未纳入正式测速'],
    ['outputs/PaddleOCR实测速率.csv','每张截图三轮耗时与均值，可用 Excel 打开'],
],[6.1,10.9])
h('复现命令')
p('在当前项目目录运行以下命令，复用现有本地 Python 环境和已准备好的模型路径。脚本关闭外部模型源连通性检查，固定随机种子，并在 GPU 推理前后同步。')
for cmd in [
    'D:\\python1\\python.exe -X utf8 -B ocr_benchmark\\benchmark.py --profile gpu_standard --rounds 3',
]:
    pp=p(cmd); pp.paragraph_format.line_spacing=1.05
    for run in pp.runs: run.font.name='Consolas'; run.font.size=Pt(9)
p('上例复现 B 组；将 profile 值替换为 gpu_full 或 gpu_960，可分别复现 A 组和 C 组。')
p('首次推理与初始化数据各为单次观测，不能视为严格冷缓存基准。CPU 探测不建议按九图三轮直接复跑，应先确定独立 CPU 环境与目标硬件。报告中的技术路线为实施建议，实际速度数据仅适用于本次记录的环境与配置。')
h('技术参考')
for text,url in [
    ('PaddleOCR 官方通用 OCR 流程与参数说明','https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.md'),
    ('PaddleOCR 3.0 技术报告','https://arxiv.org/abs/2507.05595'),
    ('Celery 官方周期任务与重复调度说明','https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html'),
]:
    pp=p(text+'\n'+url)
    for run in pp.runs: run.font.size=Pt(9)
path=OUT/'人员证书预警与替补推荐系统技术报告.docx'
doc.save(path)
print(str(path))
print('paragraphs',len(doc.paragraphs),'tables',len(doc.tables))
