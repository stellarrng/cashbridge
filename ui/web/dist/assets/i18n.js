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
    document.addEventListener("cb:theme", paint);
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
    "nav.portals": ["One case, two sides", "Một hồ sơ, hai bên cùng theo dõi", "一份材料，双方同步"],
    "land.trust": ["Measured trust", "Độ tin cậy đo được", "可度量的信任"],
    "nav.signin": ["Sign in", "Đăng nhập", "登录"], "auth.signedOut": ["Signed out. The session was ended on the server.", "Đã đăng xuất. Phiên đã được kết thúc trên máy chủ.", "已退出，会话已在服务器端结束。"],
    "hero.kicker": ["For export SMEs and the banks that fund them", "Dành cho doanh nghiệp xuất khẩu vừa và nhỏ và ngân hàng tài trợ", "面向出口型中小企业及为其融资的银行"],
    "hero.title": ["Stay ahead of cash flow. Make financing decisions with confidence.", "Dự báo thiếu hụt dòng tiền. Chuẩn bị phương án vốn có căn cứ.", "提前掌握现金流，有据可依地做融资决策。"],
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
    "lc.robust": ["{a}% → {b}%", "{a}% → {b}%", "{a}% → {b}%"],
    "chart.title": ["13-week cash forecast", "Dự báo dòng tiền 13 tuần", "13周现金流预测"],
    "chart.base": ["Without funding", "Chưa có tài trợ", "未融资"],
    "chart.bridged": ["With the recommended advance", "Với khoản ứng trước được đề xuất", "采用推荐的预付款"],
    "chart.gap": ["first negative week, found by the forecast", "tuần âm tiền đầu tiên, do mô hình dự báo tìm ra", "预测发现的首个现金为负的周"],
    "chart.bridge": ["cheapest option that covers it", "phương án rẻ nhất đủ bù tuần đó", "能覆盖缺口的最便宜方案"],
    "chart.residual": ["scenarios that never run short: one advance vs the recommended plan", "tỷ lệ kịch bản không thiếu tiền: một khoản ứng so với phương án đề xuất", "从不缺现金的情景占比：单笔预付 vs 推荐方案"],
    "flow.title": ["How a case runs", "Một hồ sơ chạy thế nào", "一个案件如何运行"],
    "flow.lede": ["One loop, five steps. The software reads the documents and does the arithmetic; people make the two decisions that matter.", "Một vòng, năm bước. Hệ thống đọc chứng từ và tính toán; con người đưa ra hai quyết định quan trọng.", "一个闭环，五个步骤。系统负责读取单据和计算，关键的两项决定由人来做。"],
    "who.agent": ["Agent", "Agent", "智能体"], "who.director": ["Director", "Giám đốc", "董事"], "who.lender": ["Lender", "Ngân hàng", "贷款方"],
    "s1.t": ["Anticipate", "Dự báo", "预判"], "s1.d": ["Forecasts 13 weeks from open invoices, deposits and payroll, and names what causes the first negative week.", "Dự báo 13 tuần từ hóa đơn chưa thu, tiền cọc và lương, chỉ ra nguyên nhân của tuần âm tiền đầu tiên.", "根据未收发票、定金和工资预测13周，并指出首个负现金周的原因。"],
    "s2.t": ["Prove", "Chứng minh", "核实"], "s2.d": ["Matches bank credits to invoices, checks each invoice against its purchase order and bill of lading, and blocks lookalike-domain payment emails.", "Khớp tiền về với hóa đơn, đối chiếu hóa đơn với đơn đặt hàng và vận đơn, chặn email giả mạo đổi tài khoản.", "将银行入账与发票匹配，核对发票与采购订单和提单，拦截仿冒域名的付款邮件。"],
    "s3.t": ["Compare", "So sánh", "比较"], "s3.d": ["Prices factoring, a bridge loan and early-payment discounts as a true annual cost, then stress-tests the choice week by week.", "Quy đổi bao thanh toán, vay bắc cầu và chiết khấu thanh toán sớm về lãi suất năm thực tế, rồi kiểm tra sức chịu đựng theo từng tuần.", "把保理、过桥贷款和提前付款折扣换算为真实年化成本，再逐周压力测试。"],
    "s4.t": ["Approve", "Phê duyệt", "批准"], "s4.d": ["Reviews the pack the accountant prepared and releases it with a one-time code bound to that exact pack. The preparer cannot approve.", "Xem hồ sơ kế toán đã lập và phát hành bằng mã một lần gắn với đúng hồ sơ đó. Người lập không được tự duyệt.", "审阅会计准备的材料包，用绑定该材料包的一次性验证码放行。准备人不能批准。"],
    "s5.t": ["Verify", "Xác minh", "核验"], "s5.d": ["Sees only what was released, recomputes every document hash and the audit chain, and records the credit decision.", "Chỉ thấy những gì đã được phát hành, tự tính lại mọi mã băm và chuỗi nhật ký, rồi ghi quyết định tín dụng.", "只能看到已放行的内容，重新计算每个单据哈希和审计链，并记录授信决定。"],
    "portals.title": ["Two portals, one evidence trail", "Hai cổng, một chuỗi bằng chứng", "两个门户，一条证据链"],
    "portals.lede": ["Each side signs in separately. Permissions are enforced by the server, so hiding a button grants nothing.", "Mỗi bên đăng nhập riêng. Quyền được kiểm tra ở máy chủ, nên ẩn một nút trên giao diện không cấp thêm quyền nào.", "双方分别登录。权限由服务器强制执行，隐藏按钮不会授予任何权限。"],
    "p.sme.t": ["SME workspace", "Cổng doanh nghiệp", "企业工作台"], "p.sme.who": ["Chief accountant prepares. Director approves.", "Kế toán trưởng lập hồ sơ. Giám đốc phê duyệt.", "总会计准备，董事批准。"],
    "p.sme.c1": ["Analyse the funding need and prepare the loan pack automatically", "Tự động phân tích nhu cầu vốn và chuẩn bị hồ sơ vay", "自动分析资金需求并准备贷款材料"],
    "p.sme.c2": ["See every figure tagged verified, calculated, estimated, assumed or missing", "Mỗi con số được gắn nhãn: đã xác minh, tính toán, ước lượng, giả định hay còn thiếu", "每个数字都标注为已核实、计算、估计、假设或缺失"],
    "p.sme.c3": ["Test what-ifs: slower buyers, smaller deposits, FX moves", "Thử kịch bản: khách trả chậm, giảm tiền cọc, biến động tỷ giá", "测试情景：买方付款变慢、定金减少、汇率变动"],
    "p.sme.c5": ["Check how safe a plan is across 2,000 scenarios before you commit", "Kiểm tra mức độ an toàn của phương án qua 2.000 kịch bản trước khi quyết định", "决策前在 2,000 个情景下检验方案的安全程度"],
    "p.sme.c4": ["Review contracts, bids, budgets and green-investment evidence", "Rà soát hợp đồng, dự án thầu, ngân sách và hồ sơ đầu tư xanh", "审查合同、投标、预算和绿色投资证据"],
    "p.sme.x1": ["The software cannot submit a pack or move money", "Hệ thống không tự nộp hồ sơ hay chuyển tiền", "系统不能自行提交材料或转账"],
    "p.sme.x2": ["The person who prepares a pack cannot approve it", "Người lập hồ sơ không thể tự phê duyệt", "准备材料包的人不能批准它"],
    "p.sme.b": ["Sign in to the SME workspace", "Đăng nhập cổng doanh nghiệp", "登录企业工作台"],
    "p.bank.t": ["Bank review", "Cổng ngân hàng", "银行审核"], "p.bank.who": ["Credit reviewer at the partner lender.", "Cán bộ thẩm định tại bên cho vay đối tác.", "合作贷款方的信贷审核员。"],
    "p.bank.c1": ["Receive packs only after the SME Director releases them", "Chỉ nhận hồ sơ sau khi Giám đốc doanh nghiệp phát hành", "仅在企业董事放行后才收到材料包"],
    "p.bank.c2": ["Recompute document, bundle and approval hashes independently", "Tự tính lại mã băm chứng từ, gói hồ sơ và phê duyệt", "独立重算单据、材料包和审批哈希"],
    "p.bank.c3": ["Read the reasoning, the assumptions and what could not be verified", "Xem lập luận, giả định và những điểm chưa kiểm chứng được", "查看推理过程、假设以及无法核实的内容"],
    "p.bank.c4": ["Approve, decline or request information, with the decision logged", "Duyệt, từ chối hoặc yêu cầu bổ sung, có ghi nhật ký", "批准、拒绝或要求补充信息，决定全程留痕"],
    "p.bank.x1": ["No access to the SME's inbox, contacts or unreleased drafts", "Không truy cập hộp thư, danh bạ hay bản nháp chưa phát hành", "无法访问企业的邮箱、联系人或未放行的草稿"],
    "p.bank.x2": ["No automated credit decision: a named person decides", "Không tự động quyết định tín dụng: một người cụ thể quyết định", "没有自动授信：由具名人员决定"],
    "p.bank.b": ["Sign in to bank review", "Đăng nhập cổng ngân hàng", "登录银行审核"],
    "trust.title": ["Trust you can measure", "Độ tin cậy đo được", "可度量的信任"],
    "trust.lede": ["Run <code>make trust</code> to reproduce these numbers. They come from the same code that serves this page.", "Chạy <code>make trust</code> để tái tạo các con số này. Chúng đến từ chính mã nguồn đang chạy trang này.", "运行 <code>make trust</code> 即可复现这些数字，它们来自运行本页面的同一套代码。"],
    "trust.sec": ["adversarial requests refused or detected: forged sessions, self-approval, replayed codes, double financing, tampered documents, prompt injection", "yêu cầu tấn công bị từ chối hoặc phát hiện: giả phiên, tự duyệt, dùng lại mã, tài trợ trùng, sửa chứng từ, chèn lệnh", "攻击性请求被拒绝或识别：伪造会话、自我审批、重放验证码、重复融资、篡改单据、提示注入"],
    "trust.agent": ["Autopilot scenarios end correctly, including the ones where the right move is to stop or hand over to a person", "kịch bản Autopilot kết thúc đúng, kể cả khi lựa chọn đúng là dừng lại hoặc chuyển cho người", "Autopilot 场景结果正确，包括应当停止或转交人工的情况"],
    "trust.model": ["Brier score of the buyer payment model against the historical-rate baseline, walk-forward on 167 synthetic invoices: synthetic data, indicative only", "điểm Brier của mô hình thanh toán so với mức cơ sở theo tỷ lệ lịch sử, kiểm tra tiến dần trên 167 hóa đơn mô phỏng: dữ liệu giả lập, chỉ mang tính tham khảo", "买方付款模型与历史比率基线的 Brier 分数，基于167张合成发票的滚动回测，合成数据，仅供参考"],
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
    "grp.decide": ["Decide", "Quyết định", "决策"], "grp.analyse": ["Analyse", "Phân tích", "分析"], "grp.control": ["Control", "Kiểm soát", "管控"], "grp.system": ["System", "Hệ thống", "系统"], "grp.account": ["Account", "Tài khoản", "账户"], "grp.review": ["Review", "Thẩm định", "审核"],
    "nav.overview": ["Overview", "Tổng quan", "总览"], "nav.autopilot": ["Autopilot", "Autopilot", "Autopilot"], "nav.core": ["Decision center", "Trung tâm quyết định", "决策中心"], "nav.cash": ["Cash forecast", "Dự báo dòng tiền", "现金流预测"],
    "nav.evidence": ["Receivables & checks", "Khoản phải thu & kiểm tra", "应收与核查"], "nav.funding": ["Funding & approval", "Tài trợ & phê duyệt", "融资与审批"],
    "nav.analytics": ["Financial health", "Sức khỏe tài chính", "财务健康"], "nav.project": ["Bid simulator", "Mô phỏng dự thầu", "投标模拟"], "nav.contracts": ["Contracts", "Hợp đồng", "合同"],
    "nav.green": ["Green finance", "Tài chính xanh", "绿色金融"], "nav.trust": ["Audit & trust", "Nhật ký & độ tin cậy", "审计与信任"], "nav.settings": ["Settings", "Cài đặt", "设置"], "nav.landing": ["Back to the home page", "Về trang giới thiệu", "返回首页"], "nav.inbox": ["Incoming packs", "Hồ sơ đến", "收到的材料包"],
    "role.note.sme_accountant": ["You prepare: analyse, choose an option and draft the funding pack. The Director approves and releases it.", "Bạn phụ trách chuẩn bị: phân tích, chọn phương án và lập hồ sơ vay. Giám đốc phê duyệt và gửi đi.", "您负责准备：分析、选择方案并起草融资材料，由董事批准并发出。"],
    "role.note.sme_director": ["You review and approve. Funding packs are prepared by the accounting team.", "Bạn có quyền xem xét và phê duyệt. Hồ sơ do bộ phận kế toán chuẩn bị.", "您负责审阅和批准，融资材料由会计部门准备。"],
    "role.note.bank_reviewer": ["You see only cases the company has released, verify them independently and record the decision.", "Bạn chỉ thấy hồ sơ doanh nghiệp đã gửi, tự kiểm tra và ghi nhận quyết định.", "您只能看到企业已提交的材料，独立核验并记录决定。"],

    // overview
    "ov.title": ["Overview", "Tổng quan", "总览"],
    "ov.lede": ["Where cash stands, why it runs short, and what is waiting for a person.", "Tiền đang ở đâu, vì sao thiếu, và việc gì đang chờ người xử lý.", "现金状况、短缺原因，以及等待人工处理的事项。"],
    "ov.cash": ["Cash today", "Tiền hiện có", "当前现金"], "ov.cashFoot": ["opening balance, synthetic bank feed", "số dư đầu kỳ, sao kê mô phỏng", "期初余额，模拟银行流水"],
    "ov.gap": ["First negative week", "Tuần âm tiền đầu tiên", "首个负现金周"], "ov.gapFoot": ["short by", "thiếu", "缺口"],
    "ov.best": ["Cheapest cover", "Phương án rẻ nhất", "最便宜的方案"], "ov.bestFoot": ["a year, total cost", "mỗi năm, tổng chi phí", "年化，总成本"],
    "ov.todo": ["Waiting for a person", "Đang chờ người xử lý", "等待人工处理"], "ov.todoFoot": ["exceptions, unmatched credits, held emails", "ngoại lệ, tiền về chưa khớp, email bị giữ", "异常、未匹配入账、被拦邮件"],
    "ov.weekly": ["Weekly closing balance", "Số dư cuối tuần", "每周期末余额"],
    "ov.weeklySub": ["Open invoices plus confirmed orders (at 90% shipment confidence); no unconfirmed sales.", "Hóa đơn đang mở cộng đơn hàng đã xác nhận (tính 90% khả năng giao); không tính doanh số chưa chốt.", "未收发票加已确认订单（按90%发货可信度）；不含未确认销售。"],
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
    "ap.lede.dir": ["You review and approve. Run the analysis in view-only mode to see the reasoning; drafting is done by the Chief accountant.", "Bạn có quyền xem xét và phê duyệt. Chạy phân tích ở chế độ chỉ xem để đọc lập luận; việc lập hồ sơ do Kế toán trưởng thực hiện.", "您负责审阅和批准。以只读模式运行分析即可查看推理过程，起草由总会计师完成。"],
    "ap.run": ["Run and draft the pack", "Chạy và soạn hồ sơ", "运行并起草材料包"], "ap.plan": ["Plan only", "Chỉ lập kế hoạch", "仅规划"], "ap.runPlan": ["Run in plan-only mode", "Chạy chế độ chỉ lập kế hoạch", "以仅规划模式运行"],
    "ap.goal": ["Goal shown to the team (it cannot change which steps run)", "Mục tiêu hiển thị cho nhóm (không thể thay đổi các bước được chạy)", "向团队展示的目标（不能改变执行的步骤）"],
    "ap.empty": ["No run yet in this session", "Chưa có lần chạy nào trong phiên này", "本次会话尚未运行"],
    "ap.emptyD": ["Run the Autopilot to go from the cash forecast to a recommendation, with every figure tagged by where it came from.", "Chạy Autopilot để đi từ dự báo dòng tiền tới đề xuất, mỗi con số đều ghi rõ nguồn.", "运行 Autopilot，从现金流预测走到建议，每个数字都标明来源。"],
    "ap.rec": ["Recommendation", "Đề xuất", "建议"], "ap.notFix": ["What it covers, what can still go wrong, and what would change it", "Phương án phủ được gì, điều gì vẫn có thể sai, và điều gì sẽ thay đổi kết luận", "方案覆盖了什么、仍可能出什么问题、以及会改变结论的因素"],
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
    "cash.lede": ["Thirteen weeks from today, built from open invoices and confirmed orders weighted by each buyer's chance of paying on time, supplier deposits, fixed costs and payroll. Unconfirmed sales are not assumed.", "13 tuần tới, dựng từ hóa đơn đang mở và đơn hàng đã xác nhận nhân với xác suất trả đúng hạn của từng khách, tiền cọc nhà cung cấp, chi phí cố định và lương. Không tính doanh số chưa chốt.", "未来13周，基于按买方准时付款概率加权的未收发票和已确认订单、供应商定金、固定成本和工资，不假设未确认的销售。"],
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

    // intelligence core
    "core.lede": ["The planning engine (Intelligence Core): compares every allowed financing plan across simulated scenarios, picks the cheapest one that meets the goal, and updates its model only after a person approves. It cannot submit, pay or change a limit.", "Bộ lập kế hoạch (Intelligence Core): so sánh mọi phương án vốn hợp lệ trên các kịch bản mô phỏng, chọn phương án rẻ nhất đạt mục tiêu, và chỉ cập nhật mô hình khi có người duyệt. Không tự nộp hồ sơ, chuyển tiền hay đổi hạn mức.", "规划引擎（Intelligence Core）：在模拟情景中比较所有合规融资方案，选出达到目标的最低成本方案，并且只在人工批准后更新模型。它不能提交、付款或修改限额。"],
    "core.goal": ["Goal", "Mục tiêu", "目标"],
    "core.goal.keep_cash_positive": ["Keep every week at or above zero", "Giữ mọi tuần không âm", "每周不低于零"],
    "core.goal.keep_above_buffer": ["Keep every week above the cash buffer", "Giữ mọi tuần trên mức đệm", "每周高于现金缓冲"],
    "core.prob": ["in at least", "trong ít nhất", "至少"], "core.ofPaths": ["of paths", "số đường", "的路径"],
    "core.run": ["Plan", "Lập kế hoạch", "规划"],
    "core.k.none": ["No action", "Không làm gì", "不采取行动"], "core.k.fixed": ["Single advance (standard rule)", "Một khoản ứng (quy trình chuẩn)", "单笔预付（标准流程）"],
    "core.k.plan": ["Recommended plan", "Phương án đề xuất", "推荐方案"], "core.k.cost": ["Expected financing cost", "Chi phí tài trợ dự kiến", "预期融资成本"],
    "core.k.foot": ["of scenarios never run short of cash", "kịch bản không thiếu tiền", "的情景不会缺现金"],
    "core.status.GOAL_MET": ["Goal met", "Đạt mục tiêu", "达成目标"], "core.status.GOAL_NOT_REACHABLE": ["Goal not reachable with allowed plans", "Không kế hoạch được phép nào đạt mục tiêu", "允许的方案均无法达成目标"],
    "core.risk": ["Chance of a negative balance, by week", "Xác suất số dư âm theo tuần", "各周出现负余额的概率"],
    "core.riskSub": ["Share of scenarios with a negative balance in each week. Lower is better.", "Tỷ lệ kịch bản có số dư âm ở từng tuần. Càng thấp càng tốt.", "各周出现负余额的情景占比，越低越好。"],
    "core.band": ["Closing balance: bad and typical scenarios", "Số dư cuối tuần: kịch bản xấu và kịch bản điển hình", "期末余额：不利情景与典型情景"],
    "core.bandSub": ["10th percentile (1 scenario in 10 is worse) and median, with and without the plan.", "Phân vị 10 (cứ 10 kịch bản có 1 kịch bản tệ hơn) và trung vị, có và không có phương án.", "第10百分位（每10个情景中有1个更差）和中位数，有无方案对比。"],
    "core.s.none": ["No action", "Không làm gì", "不采取行动"], "core.s.fixed": ["Single advance", "Một khoản ứng", "单笔预付"], "core.s.plan": ["Recommended plan", "Phương án đề xuất", "推荐方案"],
    "core.s.noneP10": ["No action, 10th pct", "Không làm gì, phân vị 10", "不采取行动，第10百分位"], "core.s.planP10": ["Recommended, 10th pct", "Phương án đề xuất, phân vị 10", "推荐方案，第10百分位"], "core.s.planP50": ["Recommended, median", "Phương án đề xuất, trung vị", "推荐方案，中位数"],
    "core.chosen": ["Recommended plan", "Phương án đề xuất", "推荐方案"],
    "core.packNote": ["Each factoring or loan is its own pack: the accountant drafts it and the Director approves it with a one-time code. The Core drafts nothing.", "Mỗi khoản factoring hay vay là một hồ sơ riêng: kế toán soạn, Giám đốc duyệt bằng mã một lần. Core không soạn hồ sơ nào.", "每笔保理或贷款都是独立材料包：由会计起草、董事用一次性验证码批准。核心不起草任何材料。"],
    "core.ranked": ["Options compared", "So sánh phương án", "方案比较"], "core.rankedSub": ["Allowed plans compared under the same simulated conditions.", "So sánh các phương án hợp lệ trên cùng điều kiện mô phỏng.", "在相同模拟条件下比较合规方案。"],
    "col.plan": ["Plan", "Kế hoạch", "方案"], "col.pgoal": ["Goal reached", "Đạt mục tiêu", "达成率"], "col.ecost": ["Expected cost", "Chi phí dự kiến", "预期成本"], "col.packs": ["Packs", "Hồ sơ", "材料包"],
    "core.rejected": ["Refused by the policy checker", "Bị bộ kiểm tra chính sách từ chối", "被政策检查器拒绝"],
    "core.constraints": ["Limits the planner cannot change", "Giới hạn planner không thể đổi", "规划器无法更改的限制"],
    "core.memory": ["Similar past quarters", "Các quý tương tự trước đây", "相似的历史季度"], "core.memorySub": ["From case memory. SIMULATED quarters are replayed in a hidden test world, not real history.", "Lấy từ bộ nhớ ca. Các quý SIMULATED được phát lại trong một thế giới kiểm tra ẩn, không phải lịch sử thật.", "来自案例记忆。SIMULATED 季度在隐藏测试世界中重放，并非真实历史。"],
    "core.met": ["goal met", "đạt", "达成"], "core.missed": ["missed", "trượt", "未达成"],
    "core.learn": ["Learning, under control", "Học có kiểm soát", "受控学习"],
    "core.learnSub": ["Outcomes are compared with what was predicted. A candidate world model must beat the active one on held-out quarters, then a different person must approve it.", "Kết quả được so với dự kiến. Mô hình thế giới mới phải tốt hơn bản đang dùng trên các quý giữ lại để kiểm tra, rồi một người khác phải duyệt.", "将结果与预测比较。候选世界模型必须在留出季度上优于当前模型，再由另一人批准。"],
    "core.active": ["Active world model", "Mô hình thế giới đang dùng", "当前世界模型"], "core.pending": ["Pending proposal", "Đề xuất đang chờ", "待审提案"],
    "core.noPending": ["No pending proposal.", "Không có đề xuất nào đang chờ.", "没有待审提案。"],
    "core.simulate": ["Let this quarter happen (simulated)", "Cho quý này diễn ra (mô phỏng)", "让本季度发生（模拟）"],
    "core.propose": ["Propose update from outcomes", "Đề xuất cập nhật từ kết quả", "根据结果提出更新"],
    "core.approve": ["Approve update", "Duyệt cập nhật", "批准更新"], "core.reject": ["Reject", "Từ chối", "拒绝"],
    "core.history": ["Model history", "Lịch sử mô hình", "模型历史"], "core.episodes": ["Quarters with outcomes", "Số quý có kết quả", "有结果的季度"],
    "core.gate": ["Held-out test", "Kiểm tra giữ lại", "留出检验"],
    "core.bench": ["Benchmark: three planners, 40 held-out quarters", "Benchmark: ba planner, 40 quý kiểm tra", "基准：三种规划器，40个留出季度"],
    "core.benchSub": ["SIMULATED. It shows whether learning corrects a wrong world model in simulation; it is not evidence about real SMEs.", "MÔ PHỎNG. Nó cho thấy việc học có sửa được mô hình sai trong mô phỏng hay không; không phải bằng chứng về SME thật.", "模拟结果。它说明学习能否在模拟中纠正错误的世界模型，并非真实中小企业的证据。"],
    "core.b.success": ["Scenarios that never run short", "Tỷ lệ kịch bản không thiếu tiền", "从不缺现金的情景占比"], "core.b.cvar": ["Shortfall in worst 5% of scenarios (CVaR 95%)", "Thiếu hụt trong 5% kịch bản xấu nhất (CVaR 95%)", "最差 5% 情景的平均缺口（CVaR 95%）"], "core.b.overconf": ["Overconfidence", "Tự tin quá mức", "过度自信"], "core.b.viol": ["Policy violations", "Vi phạm chính sách", "政策违规"], "core.b.stable": ["Outcome within 5 points after 3% noise", "Kết quả lệch ≤ 5 điểm khi nhiễu 3%", "3%噪声下结果变化≤5个百分点"], "core.b.same": ["Same plan after 3% noise (re-plan)", "Giữ nguyên kế hoạch khi nhiễu 3%", "3%噪声下保持同一方案"],
    "core.empty": ["No plan yet. Run the analysis to see options.", "Chưa có phương án. Chạy phân tích để xem các lựa chọn.", "尚无方案。运行分析以查看选项。"],
    "core.open": ["Open the Intelligence Core", "Mở Lõi điều phối", "打开智能核心"],
    "core.outcome": ["Quarter outcome", "Kết quả quý", "季度结果"],
    "core.events": ["Events and the Director's inbox", "Sự kiện và Hộp thư Giám đốc", "事件与董事收件箱"],
    "core.eventsSub": ["When something happens, the Core re-plans at once. Only events that need a decision reach the Director; the rest go to the digest. Demo events are buttons; in production they come from the bank feed, ERP and inbox.", "Khi có chuyện xảy ra, Core lập lại kế hoạch ngay. Chỉ sự kiện cần quyết định mới tới Giám đốc; còn lại vào bản tóm tắt. Trong demo sự kiện là nút bấm; khi chạy thật chúng đến từ sao kê ngân hàng, ERP và hộp thư.", "发生事件时，核心立即重新规划。只有需要决策的事件才送达董事，其余进入摘要。演示中事件是按钮；生产环境中来自银行流水、ERP 和收件箱。"],
    "core.ev.buyer_delay": ["Oakline pays 30 days late", "Oakline trả trễ 30 ngày", "Oakline 延迟30天付款"],
    "core.ev.order_cancelled": ["Harbor cancels order SO-2303", "Harbor hủy đơn SO-2303", "Harbor 取消订单 SO-2303"],
    "core.ev.deposit_up": ["Supplier asks 40% deposit", "Nhà cung cấp đòi cọc 40%", "供应商要求40%定金"],
    "core.ev.early_payment": ["Kyoto pays INV-1033 early", "Kyoto trả sớm INV-1033", "Kyoto 提前支付 INV-1033"],
    "core.evReset": ["Reset events", "Đặt lại sự kiện", "重置事件"],
    "core.inbox": ["Director inbox", "Hộp thư Giám đốc", "董事收件箱"], "core.digest": ["Digest: handled, no action needed", "Tóm tắt: đã xử lý, không cần làm gì", "摘要：已处理，无需操作"],
    "core.accept": ["Accept new plan", "Chấp nhận kế hoạch mới", "接受新方案"], "core.keep": ["Keep current plan", "Giữ kế hoạch hiện tại", "保留现有方案"],
    "core.evCount": ["{e} events → {a} for the Director", "{e} sự kiện → {a} cần Giám đốc", "{e}个事件 → {a}个需董事处理"],
    "core.inForce": ["Plan in force", "Phương án đang áp dụng", "现行方案"],
    "core.considered": ["{n} plans scored, {r} refused by the checker, {m} reach the goal", "Đã chấm {n} kế hoạch, bộ kiểm tra từ chối {r}, {m} đạt mục tiêu", "已评分 {n} 个方案，检查器拒绝 {r} 个，{m} 个达成目标"],
    "core.noEvents": ["Nothing here yet.", "Chưa có mục nào.", "暂无内容。"],
    "core.why": ["Why", "Lý do", "原因"],
    "core.tab.decide": ["Decision", "Quyết định", "决策"], "core.tab.analysis": ["Analysis", "Phân tích", "分析"], "core.tab.evidence": ["Evidence & model", "Bằng chứng & mô hình", "证据与模型"],
    "core.dc.title": ["Decision center", "Trung tâm quyết định", "决策中心"],
    "core.dc.lede": ["What is at risk, what has been done, and what needs your decision. Details are one tab away.", "Rủi ro hiện tại, việc đã xử lý và việc cần bạn quyết định. Chi tiết ở tab bên cạnh.", "当前风险、已处理事项以及需要您决定的事项。详情在旁边的标签页。"],
    "core.dc.need": ["{n} decision(s) waiting for the Director", "{n} việc đang chờ Giám đốc quyết định", "{n} 项决策等待董事处理"],
    "core.dc.none": ["Nothing needs a decision right now", "Hiện không có việc gì cần quyết định", "目前没有需要决策的事项"],
    "core.dc.sub": ["The plan is re-checked after every event. You are asked only when the plan in force gets worse, the goal can no longer be met, or the cash gap comes sooner.", "Hệ thống kiểm tra lại phương án sau mỗi sự kiện và chỉ chuyển cho bạn khi phương án đang dùng xấu đi, không còn đạt mục tiêu, hoặc thiếu tiền đến sớm hơn.", "每个事件后都会重新检查方案。只有当现行方案变差、无法达成目标或资金缺口提前时，才会请您处理。"],
    "core.dc.inboxSub": ["Sorted by priority: damage × certainty ÷ weeks left.", "Xếp theo ưu tiên: thiệt hại × độ chắc chắn ÷ số tuần còn lại.", "按优先级排序：损失 × 确定性 ÷ 剩余周数。"],
    "core.dc.empty": ["No decisions waiting. New events will appear here only if they need you.", "Không có việc chờ quyết định. Sự kiện mới chỉ xuất hiện ở đây khi cần bạn.", "没有待决事项。新事件只有在需要您时才会出现在这里。"],
    "core.dc.decided": ["{n} decided", "{n} việc đã quyết", "已决定 {n} 项"], "core.dc.digest": ["Digest: {n} handled without you", "Tóm tắt: {n} việc đã xử lý không cần bạn", "摘要：{n} 项无需您处理"],
    "core.dc.simulate": ["Simulate an event (demo)", "Giả lập sự kiện (demo)", "模拟事件（演示）"],
    "core.dc.compare": ["Compare plans", "So sánh kế hoạch", "比较方案"], "core.dc.evidence": ["Evidence & model", "Bằng chứng & mô hình", "证据与模型"],
    "core.dc.notCredit": ["Simulated plan, not a credit approval: each pack still goes to the lender.", "Kế hoạch mô phỏng, không phải phê duyệt tín dụng: mỗi hồ sơ vẫn phải qua ngân hàng.", "模拟方案，并非授信批准：每个材料包仍需提交银行。"],
    "core.deadline": ["deadline", "hạn", "截止"], "core.whatif": ["What-if sliders (Cash forecast)", "Thanh trượt what-if (Dự báo dòng tiền)", "情景滑块（现金流预测）"],
    "core.allPlans": ["All {n} ranked plans", "Toàn bộ {n} kế hoạch đã xếp hạng", "全部 {n} 个已排序方案"],
    "core.wm": ["World model and simulation", "Mô hình thế giới và mô phỏng", "世界模型与模拟"],
    "wq.approve": ["Packs to approve", "Hồ sơ chờ duyệt", "待批准材料包"], "wq.approveF": ["release with a one-time code", "phát hành bằng mã một lần", "用一次性验证码放行"],
    "wq.alerts": ["Inbox alerts", "Cảnh báo trong hộp thư", "收件箱警报"], "wq.alertsF": ["only events that need a decision", "chỉ sự kiện cần quyết định", "仅需决策的事件"],
    "wq.model": ["Model update to review", "Cập nhật mô hình chờ duyệt", "待审模型更新"], "wq.modelF": ["proposed by the accountant", "do kế toán đề xuất", "由会计提出"],
    "wq.lender": ["Lender decisions", "Quyết định của ngân hàng", "银行决定"], "wq.lenderF": ["recorded by a named reviewer", "do người thẩm định đứng tên ghi", "由具名审核员记录"],
    "wq.exceptions": ["Exceptions to resolve", "Ngoại lệ cần xử lý", "待处理异常"], "wq.exceptionsF": ["3-way match and unreadable scans", "đối chiếu 3 bên và bản quét không đọc được", "三单匹配与无法识别的扫描件"],
    "wq.unmatched": ["Credits to reconcile", "Tiền về cần đối soát", "待对账入账"], "wq.unmatchedF": ["bank lines without an invoice", "dòng sao kê chưa khớp hóa đơn", "未匹配发票的银行流水"],
    "wq.held": ["Held emails", "Email bị giữ", "被拦截邮件"], "wq.heldF": ["payee change or injection attempts", "đổi tài khoản nhận hoặc chèn lệnh", "更改收款人或注入尝试"],
    "wq.prepare": ["Pack to prepare", "Hồ sơ cần lập", "待准备材料包"], "wq.prepareF": ["No funding pack yet. Start the analysis to create a draft.", "Chưa có hồ sơ tài trợ. Bắt đầu phân tích để tạo bản nháp.", "尚无融资材料。开始分析以生成草稿。"],
    "tr2.title": ["How this recommendation was reached", "Đề xuất này được đưa ra như thế nào", "此建议是如何得出的"],
    "tr2.sub": ["Five steps from the run behind the numbers on this page. Open a step to see its evidence.", "Năm bước của lần phân tích tạo ra các số liệu trên trang. Mở từng bước để xem căn cứ.", "生成本页数字的那次分析的五个步骤。展开可查看依据。"],
    "tr2.risk": ["Risk detected", "Phát hiện rủi ro", "发现风险"], "tr2.evidence": ["Documents checked", "Kiểm tra chứng từ", "核对单据"],
    "tr2.scenarios": ["Scenarios tested", "Chạy kịch bản", "测试情景"], "tr2.rec": ["Recommendation", "Phương án đề xuất", "建议方案"],
    "tr2.approval": ["Human approval", "Phê duyệt", "人工审批"],
    "tr2.st.done": ["done", "xong", "完成"], "tr2.st.attention": ["needs attention", "cần lưu ý", "需关注"], "tr2.st.wait": ["waiting", "đang chờ", "等待中"],
    "tr2.events": ["Events since the last plan", "Sự kiện từ lần phân tích trước", "上次规划后的事件"],
    "tr2.risk.s": ["Week {w} short by {a}; {p} of scenarios stay positive without action", "Tuần {w} thiếu {a}; nếu không làm gì, {p} kịch bản đủ tiền", "第{w}周缺口 {a}；不采取行动时 {p} 的情景资金充足"],
    "tr2.risk.none": ["No negative week in the base case", "Kịch bản cơ sở không có tuần nào âm tiền", "基准情景无负现金周"],
    "tr2.risk.b1": ["Lowest base-case balance: {a}", "Số dư thấp nhất (kịch bản cơ sở): {a}", "基准情景最低余额：{a}"],
    "tr2.risk.b2": ["Without action, {p} of {n} simulated scenarios never go negative", "Nếu không làm gì, {p} trong {n} kịch bản mô phỏng không bị âm tiền", "不采取行动时，{n} 个模拟情景中 {p} 从未出现负值"],
    "tr2.ev.s": ["{ok} of {n} open invoices pass the 3-way match; {x} cannot back financing", "{ok}/{n} hóa đơn khớp đủ 3 chứng từ; {x} hóa đơn không dùng được để vay", "{ok}/{n} 张发票通过三单匹配；{x} 张不能用于融资"],
    "tr2.ev.b1": ["{n} invoices are eligible to pledge", "{n} hóa đơn đủ điều kiện thế chấp", "{n} 张发票可用于质押"],
    "tr2.ev.b2": ["{n} confirmed orders are counted in the forecast but never pledged", "{n} đơn hàng đã xác nhận được tính vào dự báo nhưng không dùng để thế chấp", "{n} 个已确认订单计入预测，但不用于质押"],
    "tr2.open": ["Open documents", "Xem chứng từ", "查看单据"],
    "tr2.sc.s": ["{n} plans scored on {p} scenarios; {r} refused by the policy check", "Chấm {n} phương án trên {p} kịch bản; {r} phương án bị chính sách loại", "在 {p} 个情景上评估 {n} 个方案；{r} 个被政策拒绝"],
    "tr2.sc.b1": ["{m} plans reach the goal ({g} of scenarios)", "{m} phương án đạt mục tiêu ({g} kịch bản)", "{m} 个方案达到目标（{g} 的情景）"],
    "tr2.sc.b2": ["Funding dates tested: week {w}", "Thời điểm giải ngân đã thử: tuần {w}", "测试的放款时间：第 {w} 周"],
    "tr2.sc.b3": ["Simulation model version", "Phiên bản mô hình mô phỏng", "模拟模型版本"],
    "tr2.feas": ["Why no allowed plan reaches {g}", "Vì sao chưa phương án hợp lệ nào đạt {g}", "为何没有合规方案达到 {g}"],
    "tr2.feas.v.LIMITED_BY_POLICY_OR_SOURCES": ["Financing could reach the goal in principle: about {n} of cash from week 1 would do it, within the {c} over-borrowing cap. A policy limit or the available sources stop the allowed plans.", "Về nguyên tắc tài trợ có thể đạt mục tiêu: cần khoảng {n} tiền mặt từ tuần 1, vẫn dưới trần vay {c}. Các phương án hợp lệ bị chặn bởi một giới hạn chính sách hoặc nguồn vốn sẵn có.", "原则上融资可以达标：从第1周起约需 {n} 现金，仍在 {c} 的过度借贷上限内。合规方案受政策限制或可用资金来源约束。"],
    "tr2.feas.v.NOT_REACHABLE_WITH_FINANCING": ["Financing alone cannot reach the goal: even {c} of free cash from week 1 (the over-borrowing cap) falls short; about {n} would be needed.", "Chỉ tài trợ thì không đạt được mục tiêu: kể cả {c} tiền mặt miễn phí từ tuần 1 (bằng trần vay) vẫn thiếu; cần khoảng {n}.", "仅靠融资无法达标：即使从第1周起获得 {c} 免费现金（过度借贷上限）仍不足，约需 {n}。"],
    "tr2.feas.probe": ["Relax one limit (same scenarios)", "Nới một giới hạn (cùng bộ kịch bản)", "放宽单项限制（相同情景）"], "tr2.feas.p": ["Scenarios meeting the goal", "Kịch bản đạt mục tiêu", "达标情景"],
    "tr2.feas.now": ["Best allowed plan today", "Phương án hợp lệ tốt nhất hiện tại", "当前最佳合规方案"],
    "tr2.feas.note": ["Diagnostic only: these are not plans and the limits do not change. Raising a limit is a policy decision for people.", "Chỉ để chẩn đoán: đây không phải phương án và giới hạn không thay đổi. Nâng giới hạn là quyết định chính sách của con người.", "仅用于诊断：这些不是方案，限制也不会改变。放宽限制是由人做出的政策决定。"],
    "tr2.feas.out": ["Options outside financing (need someone to agree)", "Lựa chọn ngoài tài trợ (cần người đồng ý)", "融资以外的选项（需相关方同意）"],
    "abl.title": ["Ablation: switch one idea off", "Ablation: tắt từng ý tưởng", "消融：逐项关闭"],
    "abl.noPlanCheck": ["Without the plan-in-force check", "Bỏ bước kiểm tra phương án đang áp dụng", "去掉现行方案检查"],
    "abl.noGroup": ["Without grouping events into cases", "Bỏ gom sự kiện thành case", "不把事件归并为案例"],
    "abl.noIncumbent": ["Same plan after 3% noise, without the plan in force (ablation)", "Giữ phương án khi nhiễu 3%, nếu không biết phương án đang áp dụng (ablation)", "3%噪声下保持同一方案（不考虑现行方案，消融）"],
    "abl.ownWorld": ["Overconfidence in the planner's own world (calibration)", "Tự tin quá mức trong chính mô hình của planner (hiệu chuẩn)", "在规划器自身模型中的过度自信（校准）"],
    "abl.ceiling": ["Why 0 of 40 reach 90%: free cash up to the over-borrowing cap from week 1 would reach 90% in {k} of {n} quarters (mean {m}). The goal is reachable in principle; the limits are packs per plan, repayment inside 13 weeks and timing. See the feasibility section of planner_benchmark.md.", "Vì sao 0/40 quý đạt 90%: nếu có tiền miễn phí bằng trần vay từ tuần 1 thì {k}/{n} quý đạt 90% (trung bình {m}). Về nguyên tắc mục tiêu đạt được; thứ chặn là số hồ sơ mỗi phương án, khoản phải trả trong 13 tuần và thời điểm giải ngân. Xem mục feasibility trong planner_benchmark.md.", "为何40个季度中0个达到90%：若从第1周起获得等于过度借贷上限的免费现金，{n}个季度中有{k}个达到90%（平均{m}）。目标原则上可达；限制在于每个方案的申请包数量、13周内还款及放款时点。详见 planner_benchmark.md 的可行性部分。"],
    "ops.notif": ["Director notifications", "Số lần báo Giám đốc", "通知总监次数"],
    "tr2.alts": ["Next best options and why they lost", "Các phương án gần nhất và lý do không chọn", "次优方案及落选原因"],
    "tr2.cvar": ["Worst 5% of scenarios (CVaR 95%): average shortfall {a} with this plan, {b} with no action.", "5% kịch bản xấu nhất (CVaR 95%): thiếu hụt trung bình {a} với phương án này, {b} nếu không làm gì.", "最差 5% 情景（CVaR 95%）：采用此方案平均缺口 {a}，不采取行动则为 {b}。"],
    "tr2.ap.inbox": ["{n} decision(s) waiting in the Director's inbox", "{n} việc đang chờ trong hộp thư Giám đốc", "董事收件箱中有 {n} 项待决"],
    "tr2.ap.pack": ["Funding pack waiting for the Director's one-time code", "Hồ sơ vay đang chờ Giám đốc nhập mã xác nhận", "融资材料包等待董事输入一次性验证码"],
    "tr2.ap.none": ["Nothing waiting for approval", "Không có gì chờ phê duyệt", "暂无待审批事项"],
    "tr2.ap.b1": ["The planner drafts nothing and sends nothing; each funding pack is prepared by the accountant.", "Hệ thống không tự lập hay gửi hồ sơ; mỗi hồ sơ vay do kế toán chuẩn bị.", "系统不会自行起草或发送材料；每个融资材料包由会计准备。"],
    "tr2.ap.b2": ["Submission to the lender needs the Director's one-time code, bound to that exact pack.", "Gửi hồ sơ cho ngân hàng cần mã xác nhận một lần của Giám đốc, gắn với đúng hồ sơ đó.", "提交给银行需要董事的一次性验证码，并绑定到该材料包。"],
    "ops.title": ["Operations benchmark: how often the Director is disturbed", "Benchmark vận hành: Giám đốc bị làm phiền bao nhiêu lần", "运营基准：董事被打扰的次数"],
    "ops.sub": ["SIMULATED. {r} raw events grouped into {c} cases; labels come from the generator, not from the router.", "MÔ PHỎNG. {r} sự kiện gốc gom thành {c} case; nhãn đúng/sai do bộ sinh dữ liệu đặt, không phải bộ định tuyến.", "模拟数据。{r} 个原始事件归并为 {c} 个案例；标签由生成器给出，而非路由器。"],
    "ops.every": ["Forward every event", "Chuyển mọi sự kiện", "转发所有事件"], "ops.threshold": ["Amount ≥ USD 10k", "Số tiền ≥ 10.000 USD", "金额 ≥ 1万美元"],
    "ops.false": ["Unnecessary alerts", "Cảnh báo không cần thiết", "不必要的提醒"], "ops.missed": ["Missed decisions", "Bỏ sót việc cần quyết", "漏报的决策"],
    "ops.precision": ["Alerts that needed the Director", "Tỷ lệ cảnh báo đúng việc của Giám đốc", "确需董事处理的提醒占比"],
    "ops.auto": ["{n} of {c} cases closed without a person; {v} safety violations.", "{n}/{c} case xử lý xong không cần người; {v} vi phạm an toàn.", "{c} 个案例中 {n} 个无需人工即完成；安全违规 {v} 次。"],
    "ops.note": ["Remaining disagreements are listed case by case in data/execution_evidence/ops_benchmark.json.", "Các ca còn lệch được liệt kê từng ca trong data/execution_evidence/ops_benchmark.json.", "其余分歧逐案列在 data/execution_evidence/ops_benchmark.json。"],
    "lbl.sim": ["Simulated", "Mô phỏng", "模拟"],
    "set.title": ["Settings", "Cài đặt", "设置"], "set.close": ["Close", "Đóng", "关闭"], "set.save": ["Save", "Lưu", "保存"], "set.saved": ["Saved on this device", "Đã lưu cài đặt trên thiết bị này", "设置已保存在本设备"],
    "set.lede": ["Display, accessibility, your account and the rules the server applies.", "Hiển thị, trợ năng, tài khoản của bạn và các quy định máy chủ áp dụng.", "显示、无障碍、您的账户以及服务器执行的规则。"],
    "set.profile": ["Account", "Tài khoản", "账户"], "set.profileSub": ["Issued by the server when you signed in.", "Do máy chủ cấp khi bạn đăng nhập.", "登录时由服务器签发。"],
    "set.orgName": ["Organisation", "Tổ chức", "组织"], "set.uid": ["User ID", "Mã người dùng", "用户 ID"], "set.tenant": ["Tenant", "Đơn vị dữ liệu", "租户"],
    "set.roleNote": ["Your role and permissions come from the signed session and cannot be changed here.", "Vai trò và quyền lấy từ phiên đăng nhập đã ký, không đổi được ở đây.", "您的角色和权限来自已签名的会话，无法在此更改。"],
    "set.display": ["Display and accessibility", "Hiển thị và trợ năng", "显示与无障碍"],
    "set.motionHint": ["Turns off animations and transitions.", "Tắt hiệu ứng và chuyển cảnh.", "关闭动画和过渡效果。"],
    "set.contrastHint": ["Stronger borders and secondary text.", "Viền và chữ phụ đậm hơn.", "边框和次要文字更清晰。"],
    "set.sessionData": ["Session and data", "Phiên và dữ liệu", "会话与数据"],
    "set.sessionSub": ["Signing out ends the session on the server, not only in this browser.", "Đăng xuất kết thúc phiên trên máy chủ, không chỉ trên trình duyệt này.", "退出会在服务器端结束会话，而不仅是在此浏览器。"],
    "set.server": ["Server", "Máy chủ", "服务器"], "set.online": ["Responding", "Đang phản hồi", "正常响应"], "set.offline": ["Not responding", "Không phản hồi", "无响应"],
    "set.expires": ["Session expires", "Phiên hết hạn lúc", "会话到期"],
    "set.personal": ["Personal", "Cá nhân", "个人"], "set.personalSub": ["Display only, saved on this device. They change nothing on the server.", "Chỉ ảnh hưởng hiển thị, lưu trên thiết bị này. Không thay đổi gì trên máy chủ.", "仅影响显示，保存在本设备，不会更改服务器上的任何内容。"],
    "set.lang": ["Language", "Ngôn ngữ", "语言"], "set.theme": ["Theme", "Giao diện", "主题"], "set.system": ["System", "Theo hệ thống", "跟随系统"], "set.light": ["Light", "Sáng", "浅色"], "set.dark": ["Dark", "Tối", "深色"],
    "set.view": ["View", "Chế độ xem", "视图"], "set.advanced": ["Advanced", "Nâng cao", "高级"], "set.simple": ["Simple", "Đơn giản", "简洁"],
    "set.viewHint": ["Simple hides analysis tabs, model evidence and technical notes; nothing is removed from the record.", "Đơn giản ẩn các tab phân tích, bằng chứng mô hình và ghi chú kỹ thuật; dữ liệu gốc vẫn được lưu đầy đủ.", "简洁模式隐藏分析标签页、模型证据和技术说明；记录本身不受影响。"],
    "set.text": ["Text size", "Cỡ chữ", "字号"], "set.normal": ["Normal", "Bình thường", "标准"], "set.large": ["Large", "Lớn", "大"],
    "set.access": ["Accessibility", "Hỗ trợ tiếp cận", "无障碍"], "set.motion": ["Reduce motion", "Giảm chuyển động", "减少动态效果"], "set.contrast": ["High contrast", "Tương phản cao", "高对比度"],
    "set.org": ["Organisation policy (read-only)", "Chính sách tổ chức (chỉ xem)", "组织策略（只读）"],
    "set.orgSub": ["Enforced by the server for every request. Shown here so you know the rules; changed only by an audited deployment.", "Máy chủ áp dụng cho mọi yêu cầu. Hiển thị để bạn biết quy định; chỉ thay đổi qua triển khai có ghi nhật ký.", "服务器对每个请求强制执行。此处仅供了解规则，只能通过有审计记录的部署来修改。"],
    "set.you": ["You", "Bạn", "您"], "set.mode": ["Mode", "Chế độ", "模式"], "set.buffer": ["Cash buffer", "Mức tiền đệm", "现金缓冲"], "set.conc": ["concentration alert", "cảnh báo tập trung", "集中度预警"],
    "set.approvals": ["Approvals", "Phê duyệt", "审批"], "set.session": ["session", "phiên", "会话"], "set.planner": ["Planner limits", "Giới hạn lập kế hoạch", "规划限制"], "set.alerts": ["Director alerts", "Cảnh báo cho Giám đốc", "董事提醒"],
    "core.peak": ["Peak risk W{w}: {a} → {b} with the plan", "Rủi ro cao nhất tuần {w}: {a} → {b} với phương án", "风险峰值第{w}周：{a} → 采用方案后 {b}"],
    "core.delta": ["Plan vs no action: {d} pts", "Phương án so với không làm gì: {d} điểm", "方案对比不采取行动：{d} 个百分点"],
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
  // The element under a tooltip is often re-rendered (click, route change), and a removed node never fires
  // pointerout: hide on any of these so a tooltip can never stay stuck on screen.
  const hideTip = () => { if (tip) tip.classList.remove("on"); };
  ["click", "scroll", "hashchange", "cb:lang", "cb:theme"].forEach((ev) => (ev === "hashchange" ? window : document).addEventListener(ev, hideTip, true));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(); });
  document.addEventListener("pointermove", (e) => {
    if (!tip || !tip.classList.contains("on")) return;
    if (!(e.target.closest && e.target.closest("[data-tip]"))) { hideTip(); return; }
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
