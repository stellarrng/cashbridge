/* Shared preferences: language (EN / VI / 中文), theme (light / dark / system) and a hover tooltip.
 * Interface text is translated here. Text produced by the engines (agent findings, cover letters,
 * evidence claims) stays in English: it is part of the hashed, number-locked record. */
(function () {
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  };

  // ------------------------------------------------------------------ theme
  const savedTheme = store.get("cb.theme");
  if (savedTheme === "light" || savedTheme === "dark") document.documentElement.dataset.theme = savedTheme;
  function currentTheme() {
    const t = document.documentElement.dataset.theme;
    if (t) return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  const SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  function themeButton(btn) {
    const paint = () => {
      const dark = currentTheme() === "dark";
      btn.innerHTML = dark ? SUN : MOON;
      btn.setAttribute("aria-label", t(dark ? "ui.light" : "ui.dark"));
      btn.title = t(dark ? "ui.light" : "ui.dark");
    };
    btn.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      store.set("cb.theme", next);
      paint();
      document.dispatchEvent(new CustomEvent("cb:theme"));
    });
    paint();
    document.addEventListener("cb:lang", paint);
  }

  // ------------------------------------------------------------------ dictionary [en, vi, zh]
  const D = {
    // shared chrome
    "lbl.week": ["Week {w}", "Tuần {w}", "第{w}周"], "lbl.in": ["in", "vào", "流入"], "lbl.out": ["out", "ra", "流出"],
    "lbl.withAdvance": ["With the advance", "Có khoản ứng trước", "含预付款"],
    "ui.light": ["Switch to light theme", "Chuyển sang giao diện sáng", "切换到浅色主题"],
    "ui.dark": ["Switch to dark theme", "Chuyển sang giao diện tối", "切换到深色主题"],
    "ui.engineNote": ["", "Nội dung do engine tạo (kết luận của agent, thư đề nghị, bằng chứng) giữ nguyên tiếng Anh vì đã được khóa số và băm.", "引擎生成的内容（智能体结论、申请函、证据）保留英文，因为它们已被锁定数字并哈希。"],

    // landing
    "nav.flow": ["How a case runs", "Quy trình một hồ sơ", "案件流程"],
    "nav.portals": ["Two portals", "Hai cổng", "两个门户"],
    "land.trust": ["Measured trust", "Độ tin cậy đo được", "可度量的信任"],
    "nav.signin": ["Sign in", "Đăng nhập", "登录"],
    "hero.kicker": ["For export SMEs and the banks that fund them", "Cho doanh nghiệp xuất khẩu vừa và nhỏ, và ngân hàng tài trợ cho họ", "面向出口型中小企业及为其融资的银行"],
    "hero.title": ["Know the week your cash runs out. Bridge it with evidence a bank can check.", "Biết trước tuần nào hết tiền. Bù khoảng thiếu bằng bằng chứng ngân hàng kiểm tra được.", "提前知道哪一周现金会断流，用银行可核验的证据来弥补缺口。"],
    "hero.lede": ["CashBridge reads your bank feed, invoices and shipping documents, forecasts 13 weeks of cash, prices every way to cover the gap, and drafts a funding pack. Your Director approves it with a one-time code; your lender re-verifies every hash.",
      "CashBridge đọc sao kê, hóa đơn và chứng từ giao hàng, dự báo dòng tiền 13 tuần, tính chi phí thật của từng cách bù thiếu hụt và soạn sẵn hồ sơ tài trợ. Giám đốc phê duyệt bằng mã một lần; ngân hàng tự kiểm lại từng mã băm.",
      "CashBridge 读取银行流水、发票和货运单据，预测未来13周现金流，计算每种补缺方案的真实成本，并起草融资材料包。董事用一次性验证码批准，贷款方重新核验每一个哈希值。"],
    "hero.sme": ["Open SME workspace", "Vào cổng doanh nghiệp", "进入企业工作台"],
    "hero.bank": ["Open bank review", "Vào cổng ngân hàng", "进入银行审核"],
    "hero.fine": ["All companies, people, lenders and bank feeds in this demo are synthetic or mocked.", "Mọi doanh nghiệp, con người, bên cho vay và dữ liệu ngân hàng trong bản demo đều là mô phỏng.", "本演示中的公司、人员、贷款方和银行数据均为合成或模拟数据。"],
    "lc.advance": ["+{a} advance", "+{a} ứng trước", "+{a} 预付款"],
    "lc.still": ["still −{a}", "vẫn thiếu {a}", "仍缺 {a}"],
    "lc.week": ["Week {w}: −{a}", "Tuần {w}: −{a}", "第{w}周：−{a}"],
    "lc.apr": ["{a} at {p}% a year", "{a}, lãi {p}%/năm", "{a}，年化 {p}%"],
    "lc.by": ["−{a} by week {w}", "−{a} vào tuần {w}", "第{w}周 −{a}"],
    "chart.title": ["13-week cash forecast", "Dự báo dòng tiền 13 tuần", "13周现金流预测"],
    "chart.base": ["Without funding", "Chưa có tài trợ", "未融资"],
    "chart.bridged": ["With the recommended advance", "Với khoản ứng trước được đề xuất", "采用推荐的预付款"],
    "chart.gap": ["first negative week, found by the forecast", "tuần âm tiền đầu tiên, do mô hình dự báo tìm ra", "预测发现的首个现金为负的周"],
    "chart.bridge": ["cheapest option that covers it", "phương án rẻ nhất đủ bù tuần đó", "能覆盖缺口的最便宜方案"],
    "chart.residual": ["what the advance does not fix; the agent says so", "phần khoản ứng không giải quyết được; agent nói rõ điều này", "预付款无法解决的部分，智能体会明确指出"],
    "flow.title": ["How a case runs", "Một hồ sơ chạy thế nào", "一个案件如何运行"],
    "flow.lede": ["One loop, five steps. The agent does the reading and arithmetic; people make the two decisions that matter.", "Một vòng, năm bước. Agent đọc và tính toán; con người đưa ra hai quyết định quan trọng.", "一个闭环，五个步骤。智能体负责读取和计算，人做出两个关键决定。"],
    "who.agent": ["Agent", "Agent", "智能体"], "who.director": ["Director", "Giám đốc", "董事"], "who.lender": ["Lender", "Ngân hàng", "贷款方"],
    "s1.t": ["Anticipate", "Dự báo", "预判"], "s1.d": ["Forecasts 13 weeks from open invoices, deposits and payroll, and names what causes the first negative week.", "Dự báo 13 tuần từ hóa đơn chưa thu, tiền cọc và lương, chỉ ra nguyên nhân của tuần âm tiền đầu tiên.", "根据未收发票、定金和工资预测13周，并指出首个负现金周的原因。"],
    "s2.t": ["Prove", "Chứng minh", "核实"], "s2.d": ["Matches bank credits to invoices, checks each invoice against its purchase order and bill of lading, and blocks lookalike-domain payment emails.", "Khớp tiền về với hóa đơn, đối chiếu hóa đơn với đơn đặt hàng và vận đơn, chặn email giả mạo đổi tài khoản.", "将银行入账与发票匹配，核对发票与采购订单和提单，拦截仿冒域名的付款邮件。"],
    "s3.t": ["Compare", "So sánh", "比较"], "s3.d": ["Prices factoring, a bridge loan and early-payment discounts as a true annual cost, then stress-tests the choice week by week.", "Quy đổi bao thanh toán, vay bắc cầu và chiết khấu thanh toán sớm về lãi suất năm thực tế, rồi kiểm tra sức chịu đựng theo từng tuần.", "把保理、过桥贷款和提前付款折扣换算为真实年化成本，再逐周压力测试。"],
    "s4.t": ["Approve", "Phê duyệt", "批准"], "s4.d": ["Reviews the pack the accountant prepared and releases it with a one-time code bound to that exact pack. The preparer cannot approve.", "Xem hồ sơ kế toán đã lập và phát hành bằng mã một lần gắn với đúng hồ sơ đó. Người lập không được tự duyệt.", "审阅会计准备的材料包，用绑定该材料包的一次性验证码放行。准备人不能批准。"],
    "s5.t": ["Verify", "Xác minh", "核验"], "s5.d": ["Sees only what was released, recomputes every document hash and the audit chain, and records the credit decision.", "Chỉ thấy những gì đã được phát hành, tự tính lại mọi mã băm và chuỗi nhật ký, rồi ghi quyết định tín dụng.", "只能看到已放行的内容，重新计算每个单据哈希和审计链，并记录授信决定。"],
    "portals.title": ["Two portals, one evidence trail", "Hai cổng, một chuỗi bằng chứng", "两个门户，一条证据链"],
    "portals.lede": ["Each side signs in separately. Permissions are enforced by the server, so hiding a button grants nothing.", "Mỗi bên đăng nhập riêng. Quyền được kiểm tra ở máy chủ, nên ẩn một nút trên giao diện không cấp thêm quyền nào.", "双方分别登录。权限由服务器强制执行，隐藏按钮不会授予任何权限。"],
    "p.sme.t": ["SME workspace", "Cổng doanh nghiệp", "企业工作台"], "p.sme.who": ["Chief accountant prepares. Director approves.", "Kế toán trưởng lập hồ sơ. Giám đốc phê duyệt.", "总会计准备，董事批准。"],
    "p.sme.c1": ["Run the Autopilot from cash gap to a drafted funding pack", "Chạy Autopilot từ khoảng thiếu tiền tới hồ sơ tài trợ đã soạn", "运行 Autopilot，从现金缺口到起草好的融资材料包"],
    "p.sme.c2": ["See every figure tagged verified, calculated, estimated, assumed or missing", "Mỗi con số được gắn nhãn: đã xác minh, tính toán, ước lượng, giả định hay còn thiếu", "每个数字都标注为已核实、计算、估计、假设或缺失"],
    "p.sme.c3": ["Test what-ifs: slower buyers, smaller deposits, FX moves", "Thử kịch bản: khách trả chậm, giảm tiền cọc, biến động tỷ giá", "测试情景：买方付款变慢、定金减少、汇率变动"],
    "p.sme.c4": ["Review contracts, bids, budgets and green-investment evidence", "Rà soát hợp đồng, dự án thầu, ngân sách và hồ sơ đầu tư xanh", "审查合同、投标、预算和绿色投资证据"],
    "p.sme.x1": ["The agent cannot submit a pack or move money", "Agent không thể nộp hồ sơ hay chuyển tiền", "智能体不能提交材料包或转账"],
    "p.sme.x2": ["The person who prepares a pack cannot approve it", "Người lập hồ sơ không thể tự phê duyệt", "准备材料包的人不能批准它"],
    "p.sme.b": ["Sign in to the SME workspace", "Đăng nhập cổng doanh nghiệp", "登录企业工作台"],
    "p.bank.t": ["Bank review", "Cổng ngân hàng", "银行审核"], "p.bank.who": ["Credit reviewer at the partner lender.", "Cán bộ thẩm định tại bên cho vay đối tác.", "合作贷款方的信贷审核员。"],
    "p.bank.c1": ["Receive packs only after the SME Director releases them", "Chỉ nhận hồ sơ sau khi Giám đốc doanh nghiệp phát hành", "仅在企业董事放行后才收到材料包"],
    "p.bank.c2": ["Recompute document, bundle and approval hashes independently", "Tự tính lại mã băm chứng từ, gói hồ sơ và phê duyệt", "独立重算单据、材料包和审批哈希"],
    "p.bank.c3": ["Read the agent's reasoning, its assumptions and what it could not check", "Đọc lập luận của agent, các giả định và những gì nó không kiểm được", "查看智能体的推理、假设及其无法核实的内容"],
    "p.bank.c4": ["Approve, decline or request information, with the decision logged", "Duyệt, từ chối hoặc yêu cầu bổ sung, có ghi nhật ký", "批准、拒绝或要求补充信息，决定全程留痕"],
    "p.bank.x1": ["No access to the SME's inbox, contacts or unreleased drafts", "Không truy cập hộp thư, danh bạ hay bản nháp chưa phát hành", "无法访问企业的邮箱、联系人或未放行的草稿"],
    "p.bank.x2": ["No automated credit decision: a named person decides", "Không tự động quyết định tín dụng: một người cụ thể quyết định", "没有自动授信：由具名人员决定"],
    "p.bank.b": ["Sign in to bank review", "Đăng nhập cổng ngân hàng", "登录银行审核"],
    "trust.title": ["Trust you can measure", "Độ tin cậy đo được", "可度量的信任"],
    "trust.lede": ["Run <code>make trust</code> to reproduce these numbers. They come from the same code that serves this page.", "Chạy <code>make trust</code> để tái tạo các con số này. Chúng đến từ chính mã nguồn đang chạy trang này.", "运行 <code>make trust</code> 即可复现这些数字，它们来自运行本页面的同一套代码。"],
    "trust.sec": ["adversarial requests refused or detected: forged sessions, self-approval, replayed codes, double financing, tampered documents, prompt injection", "yêu cầu tấn công bị từ chối hoặc phát hiện: giả phiên, tự duyệt, dùng lại mã, tài trợ trùng, sửa chứng từ, chèn lệnh", "攻击性请求被拒绝或识别：伪造会话、自我审批、重放验证码、重复融资、篡改单据、提示注入"],
    "trust.agent": ["Autopilot scenarios end correctly, including the ones where the right move is to stop or hand over to a person", "kịch bản Autopilot kết thúc đúng, kể cả khi lựa chọn đúng là dừng lại hoặc chuyển cho người", "Autopilot 场景结果正确，包括应当停止或转交人工的情况"],
    "trust.model": ["Brier score of the buyer payment model against the historical-rate baseline, walk-forward on 18 synthetic invoices: indicative only", "điểm Brier của mô hình thanh toán so với mức cơ sở theo tỷ lệ lịch sử, kiểm tra tiến dần trên 18 hóa đơn mô phỏng: chỉ mang tính tham khảo", "买方付款模型与历史比率基线的 Brier 分数，基于18张合成发票的滚动回测，仅供参考"],
    "cl.works": ["Working in this demo", "Chạy thật trong demo", "演示中真实运行"], "cl.works.d": ["Forecast, matching, APR, coverage and stress engines; OTP-bound approval; hash-chained audit log and invoice registry; server-side roles for both portals.", "Các engine dự báo, đối soát, APR, độ phủ và stress test; phê duyệt OTP gắn hành động; nhật ký và sổ đăng ký hóa đơn nối chuỗi băm; phân quyền phía máy chủ cho cả hai cổng.", "预测、匹配、年化成本、覆盖和压力测试引擎；绑定动作的一次性验证码审批；哈希链审计日志和发票登记；两个门户的服务器端角色权限。"],
    "cl.mock": ["Mocked", "Mô phỏng", "模拟"], "cl.mock.d": ["Bank feeds, the lender connector and its price list, buyer KYC. The data set is synthetic.", "Dữ liệu ngân hàng, kết nối và biểu phí bên cho vay, KYC người mua. Bộ dữ liệu là tổng hợp.", "银行流水、贷款方接口及其价目、买方 KYC。数据集为合成数据。"],
    "cl.not": ["Not claimed", "Không tuyên bố", "不作声明"], "cl.not.d": ["Cross-lender duplicate checks, production identity management, legal review of contracts, credit approval, green taxonomy certification.", "Kiểm tra tài trợ trùng giữa các ngân hàng, quản lý danh tính production, thẩm định pháp lý hợp đồng, phê duyệt tín dụng, chứng nhận phân loại xanh.", "跨贷款方重复融资检查、生产级身份管理、合同法律审查、授信审批、绿色分类认证。"],
    "foot": ["Built for the 2026 Shenzhen International FinTechathon, Topic E: SME Finance Copilot. Synthetic data only; not a bank, not financial advice.", "Xây dựng cho FinTechathon Quốc tế Thâm Quyến 2026, Chủ đề E: SME Finance Copilot. Chỉ dùng dữ liệu mô phỏng; không phải ngân hàng, không phải tư vấn tài chính.", "为2026深圳国际金融科技大赛 E 题（中小企业财务助手）而建。仅使用合成数据；不是银行，也不构成财务建议。"],
    "foot.api": ["API reference", "Tài liệu API", "API 文档"],
    "auth.sme": ["SME workspace", "Cổng doanh nghiệp", "企业工作台"], "auth.bank": ["Bank review", "Cổng ngân hàng", "银行审核"],
    "auth.sme.title": ["Sign in to your company's workspace", "Đăng nhập không gian làm việc của doanh nghiệp", "登录企业工作台"],
    "auth.sme.lede": ["The Chief accountant prepares funding packs; the Director approves them. Pick a demo account to see each side.", "Kế toán trưởng lập hồ sơ tài trợ; Giám đốc phê duyệt. Chọn tài khoản demo để xem từng vai trò.", "总会计准备融资材料包，董事批准。选择演示账户查看各方视角。"],
    "auth.bank.title": ["Sign in to the lender's review desk", "Đăng nhập cổng thẩm định của ngân hàng", "登录贷款方审核台"],
    "auth.bank.lede": ["You see only packs the SME Director released with a one-time code, and you recompute every hash before deciding.", "Bạn chỉ thấy hồ sơ Giám đốc doanh nghiệp đã phát hành bằng mã một lần, và tự kiểm lại mọi mã băm trước khi quyết định.", "您只能看到企业董事用一次性验证码放行的材料包，并在决定前重算每个哈希。"],
    "auth.demo": ["Demo accounts", "Tài khoản demo", "演示账户"],
    "auth.demo.d": ["One click signs you in. Passcodes are public because the data is synthetic.", "Bấm một lần để đăng nhập. Mật mã công khai vì dữ liệu là mô phỏng.", "单击即可登录。数据为合成数据，因此口令公开。"],
    "auth.loading": ["Loading accounts…", "Đang tải tài khoản…", "正在加载账户…"],
    "auth.form": ["Or sign in with a passcode", "Hoặc đăng nhập bằng mật mã", "或使用口令登录"],
    "auth.user": ["Account ID", "Mã tài khoản", "账户 ID"], "auth.pass": ["Passcode", "Mật mã", "口令"], "auth.submit": ["Sign in", "Đăng nhập", "登录"],
    "auth.off": ["Demo accounts are switched off on this server. Use the passcode form.", "Máy chủ này đã tắt tài khoản demo. Hãy đăng nhập bằng mật mã.", "此服务器已关闭演示账户，请使用口令登录。"],
    "auth.back.sme": ["Back to your workspace", "Quay lại không gian làm việc", "返回工作台"], "auth.back.bank": ["Back to bank review", "Quay lại cổng ngân hàng", "返回银行审核"],
    "role.sme_accountant": ["Chief accountant (preparer)", "Kế toán trưởng (người lập)", "总会计（准备人）"],
    "role.sme_director": ["Director (approver)", "Giám đốc (người duyệt)", "董事（批准人）"],
    "role.bank_reviewer": ["Credit reviewer", "Cán bộ thẩm định tín dụng", "信贷审核员"],

    // app chrome
    "app.sme": ["SME workspace", "Cổng doanh nghiệp", "企业工作台"], "app.bank": ["Bank review", "Cổng ngân hàng", "银行审核"],
    "app.assistant": ["Assistant", "Trợ lý", "助手"], "app.switch": ["Switch account", "Đổi tài khoản", "切换账户"], "app.logout": ["Sign out", "Đăng xuất", "退出"],
    "app.loading": ["Loading…", "Đang tải…", "加载中…"], "app.error": ["Something went wrong", "Đã xảy ra lỗi", "出现错误"],
    "app.viewAs": ["View as", "Xem với vai trò", "切换视角"],
    "grp.decide": ["Decide", "Quyết định", "决策"], "grp.analyse": ["Analyse", "Phân tích", "分析"], "grp.control": ["Control", "Kiểm soát", "管控"], "grp.review": ["Review", "Thẩm định", "审核"],
    "nav.overview": ["Overview", "Tổng quan", "总览"], "nav.autopilot": ["Autopilot", "Autopilot", "Autopilot"], "nav.cash": ["Cash forecast", "Dự báo dòng tiền", "现金流预测"],
    "nav.evidence": ["Receivables & checks", "Khoản phải thu & kiểm tra", "应收与核查"], "nav.funding": ["Funding & approval", "Tài trợ & phê duyệt", "融资与审批"],
    "nav.analytics": ["Financial health", "Sức khỏe tài chính", "财务健康"], "nav.project": ["Bid simulator", "Mô phỏng dự thầu", "投标模拟"], "nav.contracts": ["Contracts", "Hợp đồng", "合同"],
    "nav.green": ["Green finance", "Tài chính xanh", "绿色金融"], "nav.trust": ["Audit & trust", "Nhật ký & độ tin cậy", "审计与信任"], "nav.inbox": ["Incoming packs", "Hồ sơ đến", "收到的材料包"],
    "role.note.sme_accountant": ["You prepare: run the Autopilot, choose an option and draft the pack. The Director releases it.", "Bạn là người lập: chạy Autopilot, chọn phương án và soạn hồ sơ. Giám đốc là người phát hành.", "您负责准备：运行 Autopilot、选择方案并起草材料包，由董事放行。"],
    "role.note.sme_director": ["You approve: review the pack and release it with a one-time code, or send it back. You never prepare.", "Bạn là người duyệt: xem hồ sơ rồi phát hành bằng mã một lần, hoặc trả lại. Bạn không lập hồ sơ.", "您负责批准：审阅材料包并用一次性验证码放行或退回，您不负责准备。"],
    "role.note.bank_reviewer": ["You see only packs the SME released, verify them independently and record the decision.", "Bạn chỉ thấy hồ sơ doanh nghiệp đã phát hành, tự xác minh và ghi quyết định.", "您只能看到企业放行的材料包，独立核验并记录决定。"],

    // overview
    "ov.title": ["Overview", "Tổng quan", "总览"],
    "ov.lede": ["Where cash stands, why it runs short, and what is waiting for a person.", "Tiền đang ở đâu, vì sao thiếu, và việc gì đang chờ người xử lý.", "现金状况、短缺原因，以及等待人工处理的事项。"],
    "ov.cash": ["Cash today", "Tiền hiện có", "当前现金"], "ov.cashFoot": ["opening balance, synthetic bank feed", "số dư đầu kỳ, sao kê mô phỏng", "期初余额，模拟银行流水"],
    "ov.gap": ["First negative week", "Tuần âm tiền đầu tiên", "首个负现金周"], "ov.gapFoot": ["short by", "thiếu", "缺口"],
    "ov.best": ["Cheapest cover", "Phương án rẻ nhất", "最便宜的方案"], "ov.bestFoot": ["a year, total cost", "mỗi năm, tổng chi phí", "年化，总成本"],
    "ov.todo": ["Waiting for a person", "Đang chờ người xử lý", "等待人工处理"], "ov.todoFoot": ["exceptions, unmatched credits, held emails", "ngoại lệ, tiền về chưa khớp, email bị giữ", "异常、未匹配入账、被拦邮件"],
    "ov.weekly": ["Weekly closing balance", "Số dư cuối tuần", "每周期末余额"],
    "ov.weeklySub": ["Open receivables only; no new sales are assumed.", "Chỉ gồm hóa đơn đang mở; chưa tính doanh số mới.", "仅含未收发票，未假设新增销售。"],
    "ov.lg.ok": ["Above buffer", "Trên mức đệm", "高于缓冲"], "ov.lg.risk": ["Below buffer", "Dưới mức đệm", "低于缓冲"], "ov.lg.neg": ["Negative", "Âm tiền", "为负"],
    "ov.buyers": ["Open receivables by buyer", "Khoản phải thu theo khách hàng", "按买方划分的应收款"],
    "ov.buyersSub": ["A share above 40% is a concentration risk.", "Tỷ trọng trên 40% là rủi ro tập trung.", "占比超过40%即为集中度风险。"],
    "ov.options": ["Annual cost of each way to bridge the gap", "Lãi suất năm của từng cách bù thiếu hụt", "各补缺方案的年化成本"],
    "ov.optionsSub": ["Total cost ÷ money received × 365 ÷ days. Lower is better.", "Tổng chi phí ÷ tiền nhận × 365 ÷ số ngày. Càng thấp càng tốt.", "总成本 ÷ 实收金额 × 365 ÷ 天数，越低越好。"],
    "ov.drivers": ["What makes week {w} negative", "Điều gì khiến tuần {w} âm tiền", "第{w}周为负的原因"],
    "ov.driversSub": ["Bars to the right add to the shortfall; the parts sum to it exactly.", "Thanh bên phải làm tăng thiếu hụt; tổng các phần đúng bằng thiếu hụt.", "向右的条形增加缺口，各部分之和恰好等于缺口。"],
    "ov.checks": ["Open invoices, three-way match", "Hóa đơn đang mở, đối chiếu 3 bên", "未收发票三方匹配"],
    "ov.next": ["Next step", "Bước tiếp theo", "下一步"],
    "ov.activity": ["Latest audit lines", "Nhật ký gần nhất", "最近审计记录"],
    "st.FUNDED_MOCK": ["funded (mock)", "đã giải ngân (mô phỏng)", "已放款（模拟）"], "st.IN_REVIEW": ["in review", "đang thẩm định", "审核中"],
    "st.DECLINED": ["declined", "từ chối", "已拒绝"], "st.INFO_REQUESTED": ["info requested", "yêu cầu bổ sung", "要求补充"],
    "st.AWAITING_APPROVAL": ["awaiting approval", "chờ duyệt", "待批准"], "st.SUBMITTED": ["submitted", "đã nộp", "已提交"],
    "st.NEEDS_HUMAN": ["needs a person", "cần người xử lý", "需人工"], "st.BOOKED": ["booked", "đã ghi sổ", "已入账"], "st.READ": ["read", "đã đọc", "已读取"],
    "st.ALLOWED": ["allowed", "cho phép", "允许"], "st.APPROVED": ["approved", "đã duyệt", "已批准"], "st.REJECTED": ["rejected", "bị từ chối", "已拒绝"],
    "st.REJECTED_BY_DIRECTOR": ["sent back by Director", "Giám đốc trả lại", "董事退回"], "st.NOT_STARTED": ["not started", "chưa bắt đầu", "未开始"],
    "opt.factoring": ["Factoring", "Bao thanh toán", "保理"], "opt.loan": ["Bridge loan", "Vay bắc cầu", "过桥贷款"], "opt.discount": ["Early-pay discount", "Chiết khấu trả sớm", "提前付款折扣"], "opt.overdraft": ["Overdraft", "Thấu chi", "透支"],
    "bk.notice": ["Only packs released by the SME Director with a one-time code appear here. Pre-submission SME data is not shared.", "Chỉ hồ sơ được Giám đốc doanh nghiệp phát hành bằng mã một lần mới xuất hiện ở đây. Dữ liệu trước khi nộp không được chia sẻ.", "只有企业董事用一次性验证码放行的材料包才会出现在这里，提交前的企业数据不会共享。"],
    "st.ELIGIBLE": ["eligible", "đạt", "合格"], "st.FLAGGED": ["flagged", "cần xem", "已标记"], "st.BLOCKED": ["blocked", "bị chặn", "已阻止"],
    "next.run": ["Run the Autopilot to get a recommendation and a draft pack.", "Chạy Autopilot để có đề xuất và bản nháp hồ sơ.", "运行 Autopilot 获取建议和材料包草稿。"],
    "next.wait": ["The pack is waiting for the Director's one-time code.", "Hồ sơ đang chờ mã một lần của Giám đốc.", "材料包正在等待董事的一次性验证码。"],
    "next.approve": ["A pack is waiting for your approval.", "Có một hồ sơ đang chờ bạn duyệt.", "有一个材料包等待您批准。"],
    "next.lender": ["Submitted. The lender is reviewing it.", "Đã nộp. Ngân hàng đang thẩm định.", "已提交，贷款方正在审核。"],
    "next.done": ["The lender has recorded its decision.", "Ngân hàng đã ghi quyết định.", "贷款方已记录决定。"],
    "next.rework": ["The Director sent the pack back. Rework it.", "Giám đốc đã trả hồ sơ. Hãy làm lại.", "董事已退回材料包，请修改。"],
    "next.prepare": ["Ask the Chief accountant to prepare the pack, or run the Autopilot in plan-only mode.", "Đề nghị Kế toán trưởng lập hồ sơ, hoặc chạy Autopilot ở chế độ chỉ lập kế hoạch.", "请总会计准备材料包，或以仅规划模式运行 Autopilot。"],
    "btn.openAutopilot": ["Open Autopilot", "Mở Autopilot", "打开 Autopilot"], "btn.openFunding": ["Open funding & approval", "Mở tài trợ & phê duyệt", "打开融资与审批"],

    // autopilot
    "ap.lede.prep": ["The agent reads the case, decides the next step from an approved list, and stops at the Director. It can draft a pack; it cannot submit one or move money.", "Agent đọc hồ sơ, tự chọn bước tiếp theo trong danh sách được phép và dừng ở Giám đốc. Nó soạn được hồ sơ nhưng không nộp được và không chuyển được tiền.", "智能体读取案件，从允许列表中选择下一步，并在董事处停下。它可以起草材料包，但不能提交或转账。"],
    "ap.lede.dir": ["You approve; you don't prepare. Run the Autopilot in plan-only mode to see its reasoning. Drafting is left to the Chief accountant.", "Bạn duyệt chứ không lập. Chạy Autopilot ở chế độ chỉ lập kế hoạch để xem lập luận. Việc soạn hồ sơ dành cho Kế toán trưởng.", "您负责批准而非准备。以仅规划模式运行 Autopilot 查看其推理，起草由总会计完成。"],
    "ap.run": ["Run and draft the pack", "Chạy và soạn hồ sơ", "运行并起草材料包"], "ap.plan": ["Plan only", "Chỉ lập kế hoạch", "仅规划"], "ap.runPlan": ["Run in plan-only mode", "Chạy chế độ chỉ lập kế hoạch", "以仅规划模式运行"],
    "ap.goal": ["Goal shown to the team (it cannot change which steps run)", "Mục tiêu hiển thị cho nhóm (không thể thay đổi các bước được chạy)", "向团队展示的目标（不能改变执行的步骤）"],
    "ap.empty": ["No run yet in this session", "Chưa có lần chạy nào trong phiên này", "本次会话尚未运行"],
    "ap.emptyD": ["Run the Autopilot to go from the cash forecast to a recommendation, with every figure tagged by where it came from.", "Chạy Autopilot để đi từ dự báo dòng tiền tới đề xuất, mỗi con số đều ghi rõ nguồn.", "运行 Autopilot，从现金流预测走到建议，每个数字都标明来源。"],
    "ap.rec": ["Recommendation", "Đề xuất", "建议"], "ap.notFix": ["What this does not fix, and what would change it", "Điều phương án này không giải quyết, và điều gì sẽ thay đổi kết luận", "此方案无法解决的问题，以及会改变结论的因素"],
    "ap.withWithout": ["Balance with and without the advance", "Số dư khi có và không có khoản ứng", "有无预付款时的余额"],
    "ap.conditions": ["Conditions the lender will check", "Điều kiện ngân hàng sẽ kiểm tra", "贷款方将核查的条件"],
    "ap.did": ["What the agent did", "Agent đã làm gì", "智能体做了什么"], "ap.didSub": ["Each step was chosen from an allowed list; the reason is recorded.", "Mỗi bước được chọn từ danh sách cho phép; lý do được ghi lại.", "每一步都从允许列表中选择，并记录原因。"],
    "ap.refused": ["Refused planner proposals", "Đề xuất bị từ chối của planner", "被拒绝的规划建议"], "ap.guardrails": ["Guardrails applied", "Các hàng rào kiểm soát", "已应用的护栏"],
    "ap.injected": ["The goal text contained instruction-like content. It was shown to people only and did not change the steps.", "Mục tiêu chứa nội dung giống lệnh. Nó chỉ hiển thị cho người và không thay đổi các bước.", "目标文本包含类似指令的内容，仅向人展示，未改变步骤。"],
    "ap.register": ["Evidence register", "Sổ bằng chứng", "证据登记"], "ap.registerSub": ["{n} entries. Filter by how much each one can be trusted.", "{n} mục. Lọc theo mức độ tin cậy.", "共 {n} 条，按可信程度筛选。"],
    "ap.all": ["All", "Tất cả", "全部"], "ap.claim": ["Claim", "Nội dung", "事项"], "ap.value": ["Value", "Giá trị", "数值"], "ap.status": ["Status", "Trạng thái", "状态"],
    "ev.VERIFIED": ["verified", "đã xác minh", "已核实"], "ev.CALCULATED": ["calculated", "tính toán", "计算所得"], "ev.MODEL_ESTIMATE": ["model estimate", "ước lượng mô hình", "模型估计"],
    "ev.ASSUMPTION": ["assumption", "giả định", "假设"], "ev.NEEDS_HUMAN": ["needs a person", "cần người xem", "需人工处理"], "ev.NOT_VERIFIABLE_HERE": ["not verifiable here", "không kiểm được tại đây", "此处无法核实"],
    "dec.AWAITING_DIRECTOR_APPROVAL": ["Waiting for the Director", "Đang chờ Giám đốc", "等待董事"], "dec.PLAN_READY_FOR_PREPARER": ["Plan ready", "Kế hoạch sẵn sàng", "规划就绪"],
    "dec.MONITOR": ["No action needed", "Chưa cần hành động", "无需操作"], "dec.HUMAN_REVIEW_REQUIRED": ["A person needs to look at this", "Cần người xem xét", "需要人工审查"],
    "dec.SUBMITTED_TO_LENDER": ["Submitted to the lender", "Đã nộp cho ngân hàng", "已提交贷款方"], "dec.FUNDED_BY_LENDER": ["Funded by the lender (mock)", "Ngân hàng đã giải ngân (mô phỏng)", "贷款方已放款（模拟）"], "dec.DECLINED_BY_LENDER": ["Declined by the lender", "Ngân hàng từ chối", "贷款方已拒绝"],
    "btn.review": ["Review and approve", "Xem và duyệt", "审阅并批准"], "btn.exceptions": ["Open the exceptions", "Mở các ngoại lệ", "查看异常"], "btn.lenderStatus": ["See the lender's status", "Xem trạng thái ngân hàng", "查看贷款方状态"],

    // cash, evidence, funding
    "cash.title": ["Cash forecast", "Dự báo dòng tiền", "现金流预测"],
    "cash.lede": ["Thirteen weeks from today, built from open invoices weighted by each buyer's chance of paying on time, supplier deposits, fixed costs and payroll. No new sales are assumed.", "13 tuần tới, dựng từ hóa đơn đang mở nhân với xác suất trả đúng hạn của từng khách, tiền cọc nhà cung cấp, chi phí cố định và lương. Chưa tính doanh số mới.", "未来13周，基于按买方准时付款概率加权的未收发票、供应商定金、固定成本和工资，未假设新增销售。"],
    "cash.short": ["Short that week", "Thiếu hụt tuần đó", "当周缺口"], "cash.ccc": ["Cash conversion cycle", "Chu kỳ chuyển đổi tiền", "现金转换周期"], "cash.blocked": ["Payment-change emails blocked", "Email đổi tài khoản bị chặn", "被拦截的改账户邮件"],
    "cash.try": ["Try a scenario", "Thử kịch bản", "尝试情景"], "cash.trySub": ["The engine recomputes the forecast; nothing is saved.", "Engine tính lại dự báo; không lưu gì cả.", "引擎重新计算预测，不保存任何内容。"],
    "cash.sl.dso": ["Buyers pay later or earlier (days)", "Khách trả muộn hoặc sớm hơn (ngày)", "买方付款推迟或提前（天）"], "cash.sl.dep": ["Supplier deposit on PO-2214 (%)", "Tiền cọc nhà cung cấp cho PO-2214 (%)", "PO-2214 供应商定金（%）"],
    "cash.sl.tar": ["Share of a hypothetical 10% US tariff we absorb (%)", "Phần thuế giả định 10% của Mỹ doanh nghiệp gánh (%)", "我方承担的假设10%美国关税比例（%）"], "cash.sl.fx": ["JPY and CNY move against USD (%)", "JPY và CNY biến động so với USD (%)", "日元和人民币兑美元变动（%）"],
    "cash.reset": ["Reset to base case", "Về kịch bản gốc", "恢复基准情景"], "cash.firstNeg": ["First negative week", "Tuần âm đầu tiên", "首个负现金周"], "cash.lowest": ["Lowest balance", "Số dư thấp nhất", "最低余额"],
    "cash.risk": ["Who is likely to pay late", "Ai có khả năng trả muộn", "谁可能延迟付款"],
    "cash.col.buyer": ["Buyer", "Khách hàng", "买方"], "cash.col.share": ["Share of open receivables", "Tỷ trọng phải thu", "应收占比"], "cash.col.late": ["Avg days late", "Số ngày trễ TB", "平均逾期天数"], "cash.col.p": ["Chance on time", "Khả năng đúng hạn", "准时概率"],
    "cash.noHist": ["No history: scored as the portfolio average", "Chưa có lịch sử: lấy trung bình danh mục", "无历史：按组合平均评分"], "cash.conc": ["over 40% concentration", "tập trung trên 40%", "集中度超40%"],
    "evd.title": ["Receivables & checks", "Khoản phải thu & kiểm tra", "应收与核查"],
    "evd.lede": ["Bank credits matched to invoices, each invoice checked against its purchase order and bill of lading, scanned documents read field by field, and suspicious emails held back.", "Tiền về được khớp với hóa đơn, hóa đơn đối chiếu với đơn hàng và vận đơn, chứng từ scan được đọc từng trường, email đáng ngờ bị giữ lại.", "银行入账与发票匹配，发票与采购订单和提单核对，扫描单据逐字段读取，可疑邮件被拦截。"],
    "evd.wire": ["One wire, three invoices", "Một lệnh chuyển, ba hóa đơn", "一笔汇款对应三张发票"], "evd.recon": ["Bank reconciliation", "Đối soát ngân hàng", "银行对账"], "evd.match": ["Three-way match of open invoices", "Đối chiếu 3 bên hóa đơn đang mở", "未收发票三方匹配"],
    "evd.scans": ["Scanned documents", "Chứng từ scan", "扫描单据"], "evd.scansSub": ["Any field below 0.85 confidence goes to a person; nothing is guessed.", "Trường nào dưới 0,85 độ tin cậy sẽ chuyển cho người; không đoán.", "置信度低于0.85的字段交由人工处理，绝不猜测。"],
    "evd.held": ["Held emails", "Email bị giữ", "被拦邮件"], "evd.heldSub": ["Emails are data, never instructions. Payee details are never changed by the system.", "Email là dữ liệu, không phải lệnh. Hệ thống không bao giờ đổi thông tin người nhận tiền.", "邮件是数据而非指令，系统从不修改收款人信息。"],
    "fund.title": ["Funding & approval", "Tài trợ & phê duyệt", "融资与审批"],
    "fund.lede.prep": ["Choose an option, prepare the pack, then hand it to the Director. You cannot approve a pack yourself.", "Chọn phương án, lập hồ sơ rồi chuyển cho Giám đốc. Bạn không thể tự duyệt.", "选择方案、准备材料包后交给董事，您不能自行批准。"],
    "fund.lede.dir": ["The Chief accountant prepares packs. You release them to the lender with a one-time code bound to that exact pack, or send them back.", "Kế toán trưởng lập hồ sơ. Bạn phát hành cho ngân hàng bằng mã một lần gắn với đúng hồ sơ, hoặc trả lại.", "总会计准备材料包，您用绑定该材料包的一次性验证码放行给贷款方，或退回。"],
    "fund.prepare": ["Prepare funding pack", "Lập hồ sơ tài trợ", "准备融资材料包"], "fund.rework": ["Rework the rejected pack", "Làm lại hồ sơ bị trả", "修改被退回的材料包"],
    "fund.approve": ["Approve with one-time code", "Duyệt bằng mã một lần", "用一次性验证码批准"], "fund.reject": ["Reject", "Trả lại", "退回"],
    "fund.ways": ["Ways to bridge the gap", "Các cách bù thiếu hụt", "补缺方案"], "fund.choose": ["Choose", "Chọn", "选择"], "fund.chosen": ["Chosen", "Đã chọn", "已选"],
    "fund.noPack": ["No pack yet", "Chưa có hồ sơ", "尚无材料包"], "fund.letter": ["Cover letter", "Thư đề nghị", "申请函"], "fund.letterSub": ["Passed the number lock: every figure is one of the locked metrics.", "Đã qua khóa số: mọi con số đều thuộc các chỉ số đã khóa.", "已通过数字锁：每个数字都来自锁定指标。"],
    "fund.pdf": ["Download pack PDF", "Tải PDF hồ sơ", "下载材料包 PDF"], "fund.tamper": ["Try to slip in an invented number", "Thử chèn một con số bịa", "尝试插入编造的数字"], "fund.dupe": ["Try to finance it twice", "Thử tài trợ hai lần", "尝试重复融资"],
    "fund.lender": ["Lender review", "Ngân hàng thẩm định", "贷款方审核"], "fund.notDone": ["Not done", "Chưa thực hiện", "未完成"],
    "col.option": ["Option", "Phương án", "方案"], "col.amount": ["Amount", "Số tiền", "金额"], "col.apr": ["Annual cost", "Lãi suất năm", "年化成本"], "col.total": ["Total cost", "Tổng chi phí", "总成本"], "col.status": ["Status", "Trạng thái", "状态"],
    "otp.title": ["Approve with a one-time code", "Duyệt bằng mã một lần", "用一次性验证码批准"], "otp.bound": ["Bound to action", "Gắn với hành động", "绑定动作"],
    "otp.code": ["6-digit code from your authenticator", "Mã 6 số từ ứng dụng xác thực", "身份验证器中的6位验证码"], "otp.approve": ["Approve and submit", "Duyệt và nộp", "批准并提交"], "otp.cancel": ["Cancel", "Hủy", "取消"],

    // other pages
    "fin.title": ["Financial health", "Sức khỏe tài chính", "财务健康"], "fin.lede": ["Ratios and a 12-month view from the synthetic ledger. Missing evidence stays missing: no proxy is silently substituted.", "Các chỉ số và bức tranh 12 tháng từ sổ cái mô phỏng. Thiếu bằng chứng thì để trống, không âm thầm thay bằng số ước lượng.", "基于合成账簿的比率和12个月视图。缺失的证据保持缺失，不会悄悄替换。"],
    "fin.trend": ["Revenue and expenses, last 12 months", "Doanh thu và chi phí 12 tháng", "近12个月收入与支出"], "fin.mix": ["Where last month's money went", "Chi phí tháng gần nhất đi đâu", "上月支出构成"],
    "fin.ratios": ["All ratios", "Tất cả chỉ số", "全部比率"], "fin.scn": ["Marketing and borrowing scenario", "Kịch bản marketing và vay vốn", "营销与借款情景"], "fin.calc": ["Calculate", "Tính", "计算"],
    "prj.title": ["Bid simulator", "Mô phỏng dự thầu", "投标模拟"], "prj.lede": ["Can the company carry the next contract? Upfront cash gap, a delayed-advance and cost-overrun stress, and the workforce gap. It does not decide the bid.", "Doanh nghiệp có gánh được hợp đồng tiếp theo? Khoảng thiếu tiền ban đầu, kịch bản tạm ứng chậm và vượt chi phí, thiếu hụt nhân lực. Không quyết định thay việc dự thầu.", "企业能否承接下一份合同？测算前期资金缺口、预付款延迟与成本超支压力及人手缺口，不替您决定是否投标。"], "prj.assess": ["Assess the bid", "Đánh giá dự thầu", "评估投标"],
    "ctr.title": ["Contracts", "Hợp đồng", "合同"], "ctr.lede": ["Read a contract locally, compare it with its invoice, flag clauses worth a second look, and draft an unsigned agreement for counsel.", "Đọc hợp đồng tại máy chủ, so với hóa đơn, gắn cờ điều khoản cần xem lại và soạn bản nháp chưa ký cho luật sư.", "在本地读取合同、与发票比对、标记需复核的条款，并起草供律师审阅的未签署协议。"],
    "grn.title": ["Green finance", "Tài chính xanh", "绿色金融"], "grn.lede": ["Organise the evidence a lender asks for before a solar or efficiency loan. Impact figures are illustrative, not certified.", "Chuẩn bị bằng chứng ngân hàng yêu cầu trước khi vay đầu tư điện mặt trời hay tiết kiệm năng lượng. Số liệu tác động chỉ minh họa, chưa được chứng nhận.", "整理贷款方在光伏或节能贷款前要求的证据。影响数据仅供示意，未经认证。"],
    "tr.title": ["Audit & trust", "Nhật ký & độ tin cậy", "审计与信任"], "tr.lede": ["Measured, reproducible evidence that the controls work, plus the live audit trail of this session.", "Bằng chứng đo được, tái tạo được rằng các kiểm soát hoạt động, cùng nhật ký kiểm toán trực tiếp của phiên này.", "可度量、可复现的控制有效性证据，以及本次会话的实时审计轨迹。"],
    "tr.verify": ["Verify the audit chain", "Kiểm tra chuỗi nhật ký", "验证审计链"], "tr.tamper": ["Edit a copy and verify it", "Sửa bản sao rồi kiểm tra", "修改副本并验证"], "tr.reset": ["Reset demo", "Đặt lại demo", "重置演示"],
    "bk.inbox": ["Incoming packs", "Hồ sơ đến", "收到的材料包"], "bk.empty": ["Nothing has been released to you yet", "Chưa có hồ sơ nào được phát hành cho bạn", "尚无放行给您的材料包"],
    "bk.emptyD": ["A pack appears here only after the SME's Director approves it with a one-time code. To see the full flow, sign in as Lan (accountant) to run the Autopilot, then as Minh (Director) to approve.", "Hồ sơ chỉ xuất hiện sau khi Giám đốc doanh nghiệp duyệt bằng mã một lần. Để xem cả quy trình, đăng nhập Lan (kế toán) chạy Autopilot, rồi Minh (Giám đốc) để duyệt.", "只有在企业董事用一次性验证码批准后，材料包才会出现在这里。要查看完整流程，请先以 Lan（会计）登录运行 Autopilot，再以 Minh（董事）登录批准。"],
    "bk.received": ["Packs received", "Hồ sơ đã nhận", "已收材料包"], "bk.awaiting": ["Awaiting your decision", "Đang chờ bạn quyết định", "待您决定"], "bk.decided": ["Decided", "Đã quyết định", "已决定"],
    "bk.verify": ["Verify before you decide", "Xác minh trước khi quyết định", "决定前先核验"], "bk.verifySub": ["Recomputes every hash from the source documents and checks both chains.", "Tính lại mọi mã băm từ chứng từ gốc và kiểm tra cả hai chuỗi.", "从源单据重算每个哈希并检查两条链。"],
    "bk.runVerify": ["Run verification", "Chạy xác minh", "运行核验"], "bk.verifyAgain": ["Verify again", "Xác minh lại", "再次核验"], "bk.notVerified": ["Not verified yet.", "Chưa xác minh.", "尚未核验。"],
    "bk.decision": ["Record the credit decision", "Ghi quyết định tín dụng", "记录授信决定"], "bk.decisionSub": ["Your decision, not the system's. A decline or an information request needs a reason.", "Quyết định của bạn, không phải của hệ thống. Từ chối hoặc yêu cầu bổ sung cần nêu lý do.", "由您而非系统决定。拒绝或要求补充信息需说明理由。"],
    "bk.record": ["Record decision", "Ghi quyết định", "记录决定"], "bk.checklist": ["Checklist", "Danh sách kiểm tra", "检查清单"], "bk.checksDonut": ["Verification result", "Kết quả xác minh", "核验结果"],
    "bk.metrics": ["Locked metrics", "Chỉ số đã khóa", "锁定指标"], "bk.invoice": ["The pledged invoice", "Hóa đơn được cầm cố", "质押发票"], "bk.forecast": ["SME forecast as submitted", "Dự báo của doanh nghiệp khi nộp", "企业提交的预测"],
    "bk.agent": ["How the SME's agent reached this", "Agent của doanh nghiệp đi tới kết luận này thế nào", "企业智能体如何得出结论"], "bk.notShared": ["Not shared with you", "Không chia sẻ với bạn", "未与您共享"],
    "bk.requested": ["Requested", "Số tiền đề nghị", "申请金额"], "bk.pledged": ["Pledged invoice", "Hóa đơn cầm cố", "质押发票"], "bk.invValue": ["Invoice value", "Giá trị hóa đơn", "发票金额"], "bk.ontime": ["Buyer on-time chance", "Khả năng khách trả đúng hạn", "买方准时概率"], "bk.reviewStatus": ["Review status", "Trạng thái thẩm định", "审核状态"],
    "chk.ok": ["passed", "đạt", "通过"], "chk.no": ["failed", "không đạt", "未通过"], "chk.na": ["cannot be proven here", "không chứng minh được tại đây", "此处无法证明"],
    "chat.title": ["CFO assistant", "Trợ lý CFO", "CFO 助手"], "chat.ask": ["Ask", "Hỏi", "提问"], "chat.close": ["Close", "Đóng", "关闭"],
  };
  const IDX = { en: 0, vi: 1, zh: 2 };
  let lang = store.get("cb.lang");
  if (!IDX.hasOwnProperty(lang)) {
    const nav = (navigator.language || "").toLowerCase();
    lang = nav.startsWith("vi") ? "vi" : nav.startsWith("zh") ? "zh" : "en";
  }

  function t(key, vars) {
    const row = D[key];
    let s = row ? (row[IDX[lang]] || row[0]) : key;
    if (vars) Object.keys(vars).forEach((k) => { s = s.replace("{" + k + "}", vars[k]); });
    return s;
  }
  function apply(root) {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : lang;
    (root || document).querySelectorAll("[data-i18n]").forEach((el) => {
      if (D[el.dataset.i18n]) el.innerHTML = t(el.dataset.i18n);
    });
    (root || document).querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  }
  function langSwitch(container) {
    container.classList.add("lang");
    container.setAttribute("role", "group");
    container.setAttribute("aria-label", "Language");
    container.innerHTML = [["en", "EN"], ["vi", "VI"], ["zh", "中文"]].map(([k, l]) => `<button type="button" data-l="${k}" aria-pressed="${k === lang}">${l}</button>`).join("");
    container.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-l]");
      if (!b || b.dataset.l === lang) return;
      lang = b.dataset.l;
      store.set("cb.lang", lang);
      container.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.l === lang)));
      apply();
      document.dispatchEvent(new CustomEvent("cb:lang"));
    });
  }

  // ------------------------------------------------------------------ tooltip for [data-tip]
  let tip;
  function ensureTip() {
    if (tip) return tip;
    tip = document.createElement("div");
    tip.className = "tip";
    tip.setAttribute("role", "tooltip");
    document.body.appendChild(tip);
    return tip;
  }
  document.addEventListener("pointerover", (e) => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (!el) return;
    const t_ = ensureTip();
    t_.textContent = el.getAttribute("data-tip");
    t_.classList.add("on");
  });
  document.addEventListener("pointermove", (e) => {
    if (!tip || !tip.classList.contains("on")) return;
    const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
    const y = e.clientY + 16 + tip.offsetHeight > window.innerHeight ? e.clientY - tip.offsetHeight - 10 : e.clientY + 16;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  });
  document.addEventListener("pointerout", (e) => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el && tip && !el.contains(e.relatedTarget)) tip.classList.remove("on");
  });

  window.I18N = { t, apply, langSwitch, themeButton, lang: () => lang, has: (k) => Boolean(D[k]) };
})();
