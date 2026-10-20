"""Section 5: financial methodology and algorithms (unchanged in substance from v9)."""

I = lambda s: f"<i>{s}</i>"  # noqa: E731

BLOCKS = [
    ("h1", "Financial methodology and algorithms", "sec:method"),
    ("p", "This section specifies each algorithm as implemented, with its notation, assumptions, parameter values and the reason for the "
          "design choice. Parameter values are quoted from the source. Where the implementation deliberately departs from a textbook "
          "method, or where a guarantee holds only approximately, the text says so. Throughout, <i>t</i> indexes forecast weeks 1, …, "
          "<i>T</i> with <i>T</i> = 13, <i>n</i> indexes Monte Carlo paths 1, …, <i>N</i>, and <i>i</i> indexes receivables. "
          "𝟙(·) denotes the indicator function, equal to 1 when its argument is true and 0 otherwise; the interest amount is written "
          "<i>I</i> with a subscript."),
    ("h2", "Thirteen-week liquidity engine", "sec:engine"),
    ("p", "Let <i>C</i><sub>0</sub> be the opening cash. The deterministic forecast is the recurrence"),
    ("eq", "<i>C<sub>t</sub></i> = <i>C</i><sub><i>t</i>−1</sub> + <i>R<sub>t</sub></i> − <i>O<sub>t</sub></i> + <i>F<sub>t</sub></i>,&nbsp;&nbsp; <i>t</i> = 1, …, <i>T</i>", "eq:recurrence"),
    ("p", "where <i>R<sub>t</sub></i> is expected receipts, <i>O<sub>t</sub></i> is scheduled outflows (weekly fixed costs, supplier "
          "deposits, and payroll in any week that contains a month start), and <i>F<sub>t</sub></i> is the net effect of a chosen "
          "financing plan. Receipts are the sum over open invoices of the amount times the probability that payment falls in week "
          "<i>t</i> (Section [[sec:timing]]). Confirmed but unbilled orders enter with their stated ship confidence and are never eligible "
          "to be pledged. A week with <i>C<sub>t</sub></i> below the buffer <i>b</i> = USD 10,000 is flagged at risk, and a week with "
          "<i>C<sub>t</sub></i> &lt; 0 a shortfall; the first such week is reported with a driver attribution that ranks the receipts and "
          "payments responsible for the gap and folds minor late drivers into a single line."),
    ("p", "Working-capital indicators use standard definitions: days sales outstanding DSO = (average receivables / revenue) × <i>D</i>, "
          "days inventory outstanding DIO = (average inventory / COGS) × <i>D</i>, days payables outstanding DPO = (average payables / "
          "COGS) × <i>D</i>, and the cash conversion cycle CCC = DIO + DSO − DPO, with <i>D</i> the number of days in the ledger period."),
    ("h2", "Receipt timing as a censored survival problem", "sec:timing"),
    ("p", "<b>Motivation.</b> The earlier rule put the on-time share <i>p</i> of an invoice on its due date and the remainder a fixed four "
          "weeks later. Real delay is neither binary nor fixed. More importantly, an invoice that is still unpaid at the forecast origin "
          "is not “late by an unknown amount”; it is right-censored: all that is known is that the payment delay exceeds the age of the "
          "invoice. Discarding such invoices, or counting them as late, biases the estimated delay distribution (downward and upward "
          "respectively). Survival analysis handles censoring correctly [3, 4]."),
    ("p", "<b>Discrete delay variable.</b> Let <i>L</i> be the payment date minus the due date, in days, so that <i>L</i> &lt; 0 is early "
          "payment. Delay is discretised into cells <i>c</i> = 0, 1, …, <i>K</i>, where cell 0 collects payments 60 or more days early, "
          "cells 1 to 180 cover days −59 to +120, and cell <i>K</i> is an absorbing “later than 120 days” tail. At forecast origin "
          "<i>o</i> only point-in-time information is used: an invoice contributes an event in cell <i>c<sub>i</sub></i> if it was paid "
          "on or before <i>o</i>; otherwise it contributes a censoring in the cell of its current age <i>o</i> − due<sub><i>i</i></sub> "
          "(provided that age is at least −60 days). Payments after <i>o</i> are never visible."),
    ("p", "<b>Kaplan–Meier hazard.</b> With <i>d<sub>c</sub></i> events in cell <i>c</i> and <i>m<sub>c</sub></i> censorings in cell "
          "<i>c</i>, the number at risk at the start of cell <i>c</i> is the number of invoices whose event or censoring lies in a cell at "
          "or after <i>c</i>:"),
    ("eq", "<i>n<sub>c</sub></i> = ∑<sub><i>c</i>′ ≥ <i>c</i></sub> ( <i>d</i><sub><i>c</i>′</sub> + <i>m</i><sub><i>c</i>′</sub> ),&nbsp;&nbsp; <i>h<sub>c</sub></i> = <i>d<sub>c</sub></i> / <i>n<sub>c</sub></i>,&nbsp;&nbsp; <i>h<sub>K</sub></i> = 1", "eq:km"),
    ("p", "The survival function and the probability mass of paying exactly in cell <i>c</i> follow:"),
    ("eq", "<i>S<sub>c</sub></i> = ∏<sub><i>c</i>′ &lt; <i>c</i></sub> ( 1 − <i>h</i><sub><i>c</i>′</sub> ),&nbsp;&nbsp; <i>f<sub>c</sub></i> = <i>S<sub>c</sub></i> · <i>h<sub>c</sub></i>,&nbsp;&nbsp; ∑<sub><i>c</i></sub> <i>f<sub>c</sub></i> = 1", "eq:survival"),
    ("p", "This is the product-limit estimator of Kaplan and Meier [3] in discrete time, which is the non-parametric maximum-likelihood "
          "estimator of the survival function under independent right-censoring. Setting <i>h<sub>K</sub></i> = 1 closes the support so "
          "that every invoice is eventually paid with probability one; mass beyond the horizon is reported separately as “expected after "
          "the horizon” and never counted as cash inside the 13 weeks."),
    ("p", "<b>Conditioning on age.</b> For an invoice already unpaid through relative day <i>a</i> at the origin, the predictive mass is "
          "renormalised on the event <i>L</i> &gt; <i>a</i>:"),
    ("eq", "<i>f<sub>c</sub></i>( <i>a</i> ) = <i>f<sub>c</sub></i> · 𝟙( <i>c</i> &gt; cell(<i>a</i>) ) / ∑<sub><i>c</i>′ &gt; cell(<i>a</i>)</sub> <i>f</i><sub><i>c</i>′</sub>", "eq:age"),
    ("p", "If no mass remains (the invoice is older than anything observed), all mass is placed in the tail cell, which conservatively "
          "removes it from the horizon."),
    ("p", "<b>Expected receipts.</b> For invoice <i>i</i> of amount <i>V<sub>i</sub></i> due on day <i>u<sub>i</sub></i>, a payment in "
          "cell <i>c</i> arrives on day <i>u<sub>i</sub></i> + <i>l</i>(<i>c</i>) and falls in week <i>w</i> = floor( max(0, day − start) "
          "/ 7 ) (zero-based). Expected weekly receipts are"),
    ("eq", "<i>R<sub>t</sub></i> = ∑<sub><i>i</i></sub> <i>V<sub>i</sub></i> ∑<sub><i>c</i></sub> <i>f<sub>c</sub></i>( <i>a<sub>i</sub></i> ) · 𝟙( <i>w<sub>i</sub></i>(<i>c</i>) = <i>t</i> )", "eq:receipts"),
    ("p", "and a Monte Carlo variant draws, independently per invoice, a cell from the categorical distribution <i>f</i>( "
          "<i>a<sub>i</sub></i> ), which is used for the forecast’s own simulation band."),
    ("p", "<b>Pooled versus buyer-specific estimation.</b> The shipped estimator is the pooled Kaplan–Meier hazard over all buyers. A "
          "buyer-specific variant was implemented and evaluated but is not used. It shrinks each buyer’s hazard toward the pooled hazard "
          "<i>h</i><super>(0)</super> with a Beta prior of strength <i>k</i> = 8 on each daily hazard,"),
    ("eq", "<i>h<sub>c</sub></i><super>(<i>b</i>)</super> = ( <i>d<sub>c</sub></i><super>(<i>b</i>)</super> + <i>k</i> · <i>h<sub>c</sub></i><super>(0)</super> ) / ( <i>n<sub>c</sub></i><super>(<i>b</i>)</super> + <i>k</i> )", "eq:shrink"),
    ("p", "which is the posterior mean of a Beta(<i>k h</i><super>(0)</super>, <i>k</i>(1 − <i>h</i><super>(0)</super>)) prior updated "
          "with <i>d</i> events in <i>n</i> trials (empirical-Bayes shrinkage in the sense of [5]). On the public sample the pooled "
          "estimator was better (WAPE 20.9% against 22.2%), which is why the simpler model is used; with about 25 invoices per buyer the "
          "extra variance of buyer-specific hazards is not repaid. The on-time probability fed to the planner is the mass up to a grace "
          "period of three days, <i>p</i> = ∑<sub><i>c</i> ≤ cell(3)</sub> <i>f<sub>c</sub></i>."),
    ("p", "<b>Accuracy measures.</b> Forecast quality is the weighted absolute percentage error and bias, aggregated over origins <i>j</i> "
          "and weeks <i>t</i> [6]:"),
    ("eq", "WAPE = ∑<sub><i>j</i>,<i>t</i></sub> | ρ<sub><i>j</i>,<i>t</i></sub> − <i>R</i><sub><i>j</i>,<i>t</i></sub> | / ∑<sub><i>j</i>,<i>t</i></sub> <i>R</i><sub><i>j</i>,<i>t</i></sub>,&nbsp;&nbsp; Bias = ∑<sub><i>j</i>,<i>t</i></sub> ( ρ<sub><i>j</i>,<i>t</i></sub> − <i>R</i><sub><i>j</i>,<i>t</i></sub> ) / ∑<sub><i>j</i>,<i>t</i></sub> <i>R</i><sub><i>j</i>,<i>t</i></sub>", "eq:wape"),
    ("p", "where <i>R</i> is realised receipts from invoices open at the origin. WAPE is preferred to MAPE because weeks with near-zero "
          "receipts would otherwise dominate; it is undefined, and reported as such, at a horizon that has no receipts."),
    ("h2", "Calibrated forecast intervals", "sec:conformal"),
    ("p", "A model’s own simulation band is only as honest as the model: on the public sample the Monte Carlo P10–P90 band covered 87.1% "
          "against a nominal 80%. Split conformal prediction [7, 8, 9] replaces it with an interval whose coverage is checked against "
          "realised errors. For each horizon <i>h</i>, collect past absolute errors (nonconformity scores) <i>s</i><sub>1</sub>, …, "
          "<i>s<sub>n</sub></i> that were realised by the origin, and take the finite-sample empirical quantile"),
    ("eq", "<i>q<sub>h</sub></i> = <i>s</i><sub>(<i>k</i>)</sub>,&nbsp;&nbsp; <i>k</i> = ceil( (<i>n</i> + 1)(1 − α) ),&nbsp;&nbsp; interval = [ ρ<sub><i>h</i></sub> − <i>q<sub>h</sub></i>, ρ<sub><i>h</i></sub> + <i>q<sub>h</sub></i> ]", "eq:conformal"),
    ("p", "with <i>q<sub>h</sub></i> = +∞ when <i>k</i> &gt; <i>n</i> (too few scores for the level). If the scores are exchangeable with "
          "the future error, 1 − α ≤ P(<i>R</i> ∈ interval) ≤ 1 − α + 1/(<i>n</i> + 1) [7, 8]. Weekly forecast errors across overlapping "
          "origins are serially dependent, so exchangeability does not strictly hold and the guarantee is approximate; this is why "
          "coverage is measured out of sample (80.6% external, 80.1% synthetic) instead of assumed."),
    ("p", "<b>Adaptive conformal inference.</b> To cope with drift, ACI [10] tracks a working miscoverage level updated online,"),
    ("eq", "α<sub><i>t</i>+1</sub> = α<sub><i>t</i></sub> + γ ( α − err<sub><i>t</i></sub> ),&nbsp;&nbsp; err<sub><i>t</i></sub> = 𝟙( <i>R<sub>t</sub></i> outside its interval )", "eq:aci"),
    ("p", "which guarantees, for any data sequence, that the average miss rate over <i>T</i> steps differs from α by at most "
          "(max{α<sub>1</sub>, 1 − α<sub>1</sub>} + γ) / (γ<i>T</i>) [10]. With α = 0.2, γ = 0.02 and a 200-score window the bound is "
          "loose for short histories. It reached 81.0% on 2,466 public invoices but only 74.0% on the 185-invoice synthetic history, so "
          "it is reported and not used; the product uses plain split conformal."),
    ("h2", "Buyer payment-risk model", "sec:buyer"),
    ("p", "<b>Specification.</b> For invoice <i>i</i> from buyer <i>b</i>, the feature vector is <b><i>x</i></b><sub><i>i</i></sub> = ( "
          "one-hot(<i>b</i>), terms<sub><i>i</i></sub> / 30, <i>V<sub>i</sub></i> / median<sub><i>b</i></sub>(<i>V</i>) ), and the model "
          "is logistic regression for the event “paid within three days of due” (<i>y</i> = 1):"),
    ("eq", "P( <i>y<sub>i</sub></i> = 1 | <b><i>x</i></b><sub><i>i</i></sub> ) = σ( β<sub>0</sub> + <b>β</b>′<b><i>x</i></b><sub><i>i</i></sub> ),&nbsp;&nbsp; σ(<i>z</i>) = 1 / (1 + <i>e</i><super>−<i>z</i></super>)", "eq:logit"),
    ("p", "<b>Estimation.</b> Coefficients minimise the L2-penalised negative log-likelihood with the intercept unpenalised and <i>C</i> = 10:"),
    ("eq", "<i>J</i>(<b>β</b>) = − ∑<sub><i>i</i></sub> [ <i>y<sub>i</sub></i> ln <i>p<sub>i</sub></i> + (1 − <i>y<sub>i</sub></i>) ln(1 − <i>p<sub>i</sub></i>) ] + (1 / 2<i>C</i>) ‖<b>β</b><sub>1:</sub>‖<super>2</super>", "eq:penalty"),
    ("p", "<i>J</i> is strictly convex, so Newton–Raphson (equivalently iteratively reweighted least squares [11]) converges to the unique "
          "minimum: <b>β</b> := <b>β</b> − <i>H</i><super>−1</super><b><i>g</i></b>, with <b><i>g</i></b> = <i>X</i>′(<b><i>p</i></b> − "
          "<b><i>y</i></b>) + diag(λ)<b>β</b> and <i>H</i> = <i>X</i>′<i>WX</i> + diag(λ), where <i>W</i> = diag(<i>p<sub>i</sub></i>(1 − "
          "<i>p<sub>i</sub></i>)), λ<sub><i>j</i></sub> = 1/<i>C</i> for penalised coordinates and 0 for the intercept. The scikit-learn "
          "solver is used when installed; the NumPy implementation of the same objective is used otherwise, and a test asserts that the "
          "two agree."),
    ("p", "<b>Safeguards.</b> Fitted probabilities are clipped to [0.02, 0.98], so the model cannot state certainty from one firm’s "
          "history; a buyer absent from the history receives the portfolio estimate and is labelled; a history with a single outcome "
          "falls back to a smoothed constant; and inputs outside the training range raise an <font name='Mono' size='9'>out_of_domain</font> "
          "warning. Concentration risk is flagged when one buyer holds more than 40% of open receivables."),
    ("p", "<b>Validation.</b> Models are evaluated with walk-forward splits, so that each prediction uses only earlier invoices. "
          "Discrimination is measured by the area under the ROC curve, AUC = P(<i>s</i><super>+</super> &gt; <i>s</i><super>−</super>) + "
          "½P(<i>s</i><super>+</super> = <i>s</i><super>−</super>), the Mann–Whitney statistic [12]; overall accuracy by the Brier score "
          "[13] = (1/<i>n</i>) ∑ (<i>p<sub>i</sub></i> − <i>y<sub>i</sub></i>)<super>2</super>; and calibration by the expected "
          "calibration error [14], ECE = ∑<sub><i>m</i></sub> (|<i>B<sub>m</sub></i>| / <i>n</i>) | mean(<i>y</i>; <i>B<sub>m</sub></i>) − "
          "mean(<i>p</i>; <i>B<sub>m</sub></i>) |, over probability bins <i>B<sub>m</sub></i>. On the synthetic history the Brier score is "
          "0.0906 with buyer identity and 0.1481 without it."),
    ("h2", "Financing options: cost and annualised rate", "sec:apr"),
    ("p", "All monetary arithmetic uses Decimal with half-up rounding to the cent. Simple interest on principal <i>P</i> at nominal rate "
          "<i>r</i> per annum for <i>d</i> days uses an Actual/365 basis, <i>I</i> = <i>P r d</i> / 365. The reported annualised cost is"),
    ("eq", "APR = ( <i>K</i> / <i>N</i> ) × ( 365 / <i>d</i> )", "eq:apr"),
    ("p", "where <i>K</i> is total financing cost, <i>N</i> is net funds actually received and <i>d</i> is days outstanding. The four "
          "products specialise this as follows."),
    ("table", ["Product", "Net funds <i>N</i>", "Total cost <i>K</i>", "Annualised cost"], [
        ["Invoice factoring (invoice <i>V</i>, advance rate <i>a</i>, fee rate <i>f</i>, rate <i>r</i>)", "<i>A</i> = <i>aV</i>", "<i>fV</i> + <i>A r d</i> / 365", "(<i>K</i> / <i>A</i>)(365 / <i>d</i>)"],
        ["Bridge loan (principal <i>P</i>, upfront fee rate φ)", "<i>P</i>(1 − φ)", "φ<i>P</i> + <i>P r d</i> / 365", "(<i>K</i> / <i>N</i>)(365 / <i>d</i>)"],
        ["Early-payment discount (rate δ, terms δ/<i>T</i> net <i>M</i>)", "<i>V</i>(1 − δ)", "δ<i>V</i>", "δ/(1 − δ) × 365 / (<i>M</i> − <i>T</i>)"],
        ["Overdraft (drawn amount <i>P</i>)", "<i>P</i>", "<i>P r d</i> / 365", "<i>r</i> (by construction)"],
    ], [2.4, 0.9, 1.3, 1.3], "tab:costs", "Cost formulae implemented in core/funding_evaluator.py."),
    ("p", "<b>Worked example (illustrative values, not catalogue terms).</b> Factor an invoice <i>V</i> = 100,000 for <i>d</i> = 60 days "
          "with <i>a</i> = 80%, <i>f</i> = 1% and <i>r</i> = 12%. Then <i>A</i> = 80,000; fee = 1,000; interest = 80,000 × 0.12 × 60 / "
          "365 = 1,578.08; <i>K</i> = 2,578.08; and APR = (2,578.08 / 80,000)(365 / 60) = 19.60%. The early-discount formula follows from "
          "requiring that giving up δ<i>V</i> to be paid <i>M</i> − <i>T</i> days sooner earns the same simple annual rate; for 2/10 net "
          "30 it gives (0.02 / 0.98)(365 / 20) = 37.24%, the figure shown for the demonstration case in Figure [[fig:provenance]], against "
          "17.12% for factoring and 18.24% for the bridge loan. Because these are simple-interest figures, an effective compounded annual "
          "rate (1 + <i>K</i>/<i>N</i>)<super>365/<i>d</i></super> − 1 is higher (21.28% in the worked example); the product reports the "
          "simple figure, labelled as CashBridge’s internal convention and not a statutory APR, because that is the convention used by the "
          "quotes it compares."),
    ("p", "<b>Eligibility.</b> A factoring option is ineligible, with the reason recorded, when the invoice failed verification, its tenor "
          "exceeds the lender’s maximum (120 days in the mock catalogue), or it is below the minimum invoice size. Options are ranked by "
          "ascending APR and each carries a <i>why not cheaper</i> statement quantifying the gap in annual percentage points."),
    ("h2", "One funding timeline: drawdown, settlement and cash effect", "sec:schedule"),
    ("p", "A FundingSchedule fixes the quote date, drawdown date and expected settlement date once; the quote, the coverage chart and the "
          "settlement scenarios all read it. For factoring the cash effect is derived as follows [15]. The buyer pays the factor, which "
          "retains the advance, the fee and interest accrued to the payment date, and remits the remainder (the rebate) to the SME. "
          "Suppose the base forecast already contains the receipt, and let <i>s<sub>k</sub></i> be the probability share of the invoice "
          "expected to be paid on date <i>t<sub>k</sub></i> (∑ <i>s<sub>k</sub></i> = 1). Relative to the base forecast the SME then "
          "experiences"),
    ("eq", "Δ<i>C</i>( drawdown ) = + <i>A</i>,&nbsp;&nbsp; Δ<i>C</i>( <i>t<sub>k</sub></i> ) = − <i>s<sub>k</sub> V</i> + <i>s<sub>k</sub></i> ( <i>V</i> − <i>A</i> − <i>F</i> − <i>I<sub>k</sub></i> ) = − <i>s<sub>k</sub></i> ( <i>A</i> + <i>F</i> + <i>I<sub>k</sub></i> )", "eq:rebate"),
    ("p", "where the first term in the second expression removes the receipt that the factor now collects and the second adds the rebate "
          "share. Summing over all <i>k</i> and over a horizon that contains every receipt gives a total of <i>A</i> − (<i>A</i> + <i>F</i> "
          "+ <i>I</i><sub>E</sub>) = −(<i>F</i> + <i>I</i><sub>E</sub>), the expected financing cost, to the cent: nothing is counted twice. "
          "A later drawdown re-prices interest for the days actually financed, and with drawdown on the quote date the schedule reproduces "
          "the quote exactly (a tested invariant)."),
    ("p", "<b>Recourse.</b> With recourse the SME repays the factor if the buyer never pays, which is modelled as default established 90 "
          "days after the due date; with non-recourse the factor bears that loss and the schedule records the difference."),
    ("h2", "Monte Carlo scenario model", "sec:mc"),
    ("p", "<b>Why simulate.</b> The forecast gives the expected balance, but a lender and a Director need the probability that a plan fails "
          "and how badly. The simulator therefore draws <i>N</i> = 2,000 (default) paths from a documented, versioned world model and "
          "replays every candidate plan on the same paths. Using common random numbers makes the difference between two plans far less "
          "noisy than either estimate alone, because the sampling error shared by both cancels [16]. Draws are seeded, so identical inputs, "
          "parameters and seed reproduce identical paths."),
    ("p", "<b>Generative model.</b> Each receivable <i>i</i> belongs to buyer <i>b</i>(<i>i</i>) and has on-time probability "
          "<i>p<sub>i</sub></i> from Section [[sec:timing]] or [[sec:buyer]]. For each path:"),
    ("bullets", [
        "a buyer slowdown indicator <i>Z<sub>b</sub></i> ~ Bernoulli(π), π = 0.05, drawn once per buyer per path so that a buyer’s invoices slow down together (this correlated risk is what a single expected path conceals);",
        "the effective on-time probability <i>q<sub>i</sub></i> = σ( logit <i>p<sub>i</sub></i> + δ<sub><i>b</i></sub> ) × ( <i>m</i> if <i>Z<sub>b</sub></i> = 1 else 1 ), with learnable per-buyer shift δ<sub><i>b</i></sub> and slowdown multiplier <i>m</i> = 0.5;",
        "payment week <i>W<sub>i</sub></i> = due week if on time (probability <i>q<sub>i</sub></i>), otherwise due week + λ + <i>e Z<sub>b</sub></i> with late delay λ = 4 weeks and slowdown extra delay <i>e</i> = 2 weeks;",
        "for a confirmed order, shipment on plan with probability min(1, <i>c<sub>i</sub> s</i>), where <i>c<sub>i</sub></i> is the stated ship confidence and <i>s</i> a learnable scale, otherwise an additional 3-week slip; an unshipped order is never cash in the week planned;",
        "one cost factor per path κ ~ LogNormal(−σ<sub><i>c</i></sub><super>2</super>/2, σ<sub><i>c</i></sub><super>2</super>) with σ<sub><i>c</i></sub> = 0.04, scaling all outflows (the offset gives E[κ] = 1), and one FX factor φ ~ N(1, 0.02<super>2</super>) scaling every foreign-currency receipt;",
        "a supplier accepts a requested deposit reduction with probability 0.6.",
    ]),
    ("p", "Path <i>n</i> then has weekly net cash <i>x</i><sub><i>n</i>,<i>t</i></sub> = inflows − outflows + plan flows, closing balance "
          "<i>C</i><sub><i>n</i>,<i>t</i></sub> = <i>C</i><sub>0</sub> + ∑<sub><i>u</i> ≤ <i>t</i></sub> <i>x</i><sub><i>n</i>,<i>u</i></sub>, "
          "trough <i>T<sub>n</sub></i> = min<sub><i>t</i></sub> <i>C</i><sub><i>n</i>,<i>t</i></sub> and shortfall <i>S<sub>n</sub></i> = "
          "max(0, −<i>T<sub>n</sub></i>). The goal probability for a floor (zero, or the buffer) is the Monte Carlo estimate"),
    ("eq", "<i>P</i><sub>goal</sub>( <i>A</i> ) = (1 / <i>N</i>) ∑<sub><i>n</i></sub> 𝟙( <i>T<sub>n</sub></i>( <i>A</i> ) ≥ floor ),&nbsp;&nbsp; SE = √( <i>P</i>(1 − <i>P</i>) / <i>N</i> )", "eq:pgoal"),
    ("p", "so that with <i>N</i> = 2,000 the standard error never exceeds 1.1 percentage points. A plan is a list of actions from a closed "
          "set; the action flows are, for factoring with advance <i>A</i> drawn in week <i>w<sub>d</sub></i> against invoice <i>i</i>,"),
    ("eq", "Δ<i>C<sub>n</sub></i>( <i>w<sub>d</sub></i> ) = +<i>A</i>,&nbsp;&nbsp; Δ<i>C<sub>n</sub></i>( <i>w</i><sub><i>s</i>,<i>n</i></sub> ) = − ( <i>A</i> + <i>F</i> + <i>I<sub>n</sub></i> ),&nbsp;&nbsp; <i>w</i><sub><i>s</i>,<i>n</i></sub> = max( <i>W</i><sub><i>i</i>,<i>n</i></sub>, <i>w<sub>d</sub></i> )", "eq:mcfactor"),
    ("eq", "<i>I<sub>n</sub></i> = <i>A</i> · <i>r</i> · max( 7, 7( <i>w</i><sub><i>s</i>,<i>n</i></sub> − <i>w<sub>d</sub></i> ) + 2 ) / 365", "eq:mcinterest"),
    ("p", "so a path on which the buyer pays late makes the financing dearer on that path, which is how the model captures the way delay "
          "inflates cost. A bridge loan adds <i>N</i> = <i>P</i> − fee at drawdown and subtracts <i>P</i> + <i>I</i> after ceil(<i>d</i>/7) "
          "weeks when repayment falls inside the horizon, and a deposit cut releases the saving only on paths where the supplier agrees. "
          "The module computes balances only and has no side effects."),
    ("p", "<b>World-model versioning.</b> Parameters are held in an immutable record whose version identifier is the first ten "
          "hexadecimal characters of the SHA-256 of its sorted JSON; every result states the version that produced it, so a changed "
          "assumption is visible as a changed identifier."),
    ("h2", "Tail risk: value-at-risk and conditional value-at-risk", "sec:cvar"),
    ("p", "For a loss variable <i>S</i> with distribution function <i>F<sub>S</sub></i> and level α = 0.95, value-at-risk is VaR<sub>α</sub> "
          "= inf{ <i>z</i> : <i>F<sub>S</sub></i>(<i>z</i>) ≥ α } and conditional value-at-risk is the mean loss beyond it. Rockafellar "
          "and Uryasev [17] show that"),
    ("eq", "CVaR<sub>α</sub>( <i>S</i> ) = min<sub>ζ</sub> { ζ + ( 1 / (1 − α) ) E[ ( <i>S</i> − ζ )<super>+</super> ] },&nbsp;&nbsp; minimiser ζ* = VaR<sub>α</sub>", "eq:cvar"),
    ("p", "which on a sample of <i>N</i> paths reduces to the average of the ceil((1 − α)<i>N</i>) largest shortfalls; this is exactly what "
          "the implementation computes (the worst 100 of 2,000 paths). CVaR is a coherent risk measure [18], so unlike VaR it is "
          "subadditive and it is always at least the 95th-percentile shortfall; it also penalises the size of the bad outcomes and not "
          "only their frequency. A shortfall variable is used, not the closing balance, so that the measure has the units of dollars of "
          "cash missing in the worst 5% of futures."),
    ("h2", "Plan search and selection", "sec:plan"),
    ("p", "<b>Candidate generation.</b> Candidate plans are enumerated, not generated by a model. For each draw week in {first week with "
          "P(negative) ≥ 10%, base-case first negative week}, the usable invoices are those with at least 14 days to due, at least the "
          "lender minimum size, and <i>p<sub>i</sub></i> ≥ 0.5, limited to the largest few. The plan set contains the empty plan; every "
          "combination of one, two or three factored invoices; the bridge loan alone; the loan with one or two factored invoices; and "
          "each of these with the supplier-deposit reduction. The count is bounded by ∑<sub><i>k</i>=1</sub><super>3</super> "
          "C(<i>m</i>, <i>k</i>) plus loan combinations, which for <i>m</i> ≤ 12 usable invoices is in the hundreds; the demonstration "
          "case scores 250 plans. Exhaustive enumeration over a small closed set is chosen over an integer-programming formulation because "
          "it is auditable: the ranked list, including the plans that lost and why, can be shown to the Director."),
    ("p", "<b>Independent validation.</b> Every candidate, including any plan injected by a caller, passes "
          "<font name='Mono' size='9'>validate_plan</font>, a checker separate from the planner. It requires (i) every action to be in the "
          "closed set; (ii) no more than three packs; (iii) every pledged invoice to be verified, unpledged and at least 14 days from due; "
          "(iv) <i>p<sub>i</sub></i> ≥ 0.5 to limit adverse selection; and (v) the over-borrowing bound"),
    ("eq", "∑<sub><i>a</i> ∈ <i>A</i></sub> funding( <i>a</i> ) ≤ 1.5 · <i>S</i><super>0</super><sub>95</sub>", "eq:cap"),
    ("p", "where <i>S</i><super>0</super><sub>95</sub> is the 95th percentile of the no-action shortfall. Plans that fail are returned with "
          "their violations."),
    ("p", "<b>Optimisation problem.</b> Selection is a sample-average approximation [19, 20] of a chance-constrained programme [21]:"),
    ("eq", "min<sub><i>A</i></sub> <i>J</i>( <i>A</i> ) = E[ <i>K</i>( <i>A</i> ) ] + λ · CVaR<sub>95</sub>( <i>S</i>( <i>A</i> ) )&nbsp;&nbsp; subject to&nbsp;&nbsp; P( <i>T</i>( <i>A</i> ) ≥ floor ) ≥ τ,&nbsp; <i>A</i> valid", "eq:objective"),
    ("p", "with <i>K</i>(<i>A</i>) the realised financing cost on a path, λ = 0.02 and τ chosen from {0.80, 0.85, 0.90, 0.95} (default 0.90 "
          "for a zero floor and 0.80 for the buffer floor). The weight λ is a fixed policy value derived, not tuned: a 5% tail probability "
          "times an assumed 40% cost of emergency funding in that tail gives 0.02, that is, the planner will pay up to USD 2 of expected "
          "cost to remove USD 100 of tail shortfall. Ties are broken lexicographically by cost, fewest packs, no need for supplier "
          "agreement, then plan identifier, so the choice is deterministic. The default objective is risk-adjusted (<i>J</i> above); a "
          "<i>cheapest</i> objective minimises E[<i>K</i>] alone and was the baseline in the benchmark."),
    ("p", "<b>When the goal is unreachable.</b> If no valid plan meets τ, the planner does not weaken it. It identifies the best achievable "
          "probability <i>p</i>* and chooses the cheapest plan whose probability lies within two standard errors of it, 2√( <i>p</i>*(1 − "
          "<i>p</i>*) / <i>N</i> ), because differences smaller than the simulation noise should not be paid for. The status is reported as "
          "GOAL_NOT_REACHABLE."),
    ("p", "<b>Stability of the recommendation.</b> To avoid asking the SME to switch plans over simulation noise, an incumbent plan is "
          "retained when it meets the same goal status, its probability is within that noise tolerance of the new best, and its expected "
          "cost is at most 1.10 times the new best plus USD 50."),
    ("p", "<b>Robust variant.</b> For the robust objective the goal probability is replaced by its worst case over a finite ambiguity set "
          "of adverse worlds <i>W</i><sub>1</sub>, …, <i>W<sub>J</sub></i>:"),
    ("eq", "<i>p</i><sub>robust</sub>( <i>A</i> ) = min<sub><i>j</i> = 1..<i>J</i></sub> P<sub><i>W<sub>j</sub></i></sub>( <i>T</i>( <i>A</i> ) ≥ floor )", "eq:robust"),
    ("p", "The set comprises: any single buyer’s odds of paying on time halving (a logit shift of ln 0.5); all buyers’ odds falling by a "
          "third together (ln 2/3); and confirmed orders shipping at 85% of stated confidence. These are fixed policy values. The "
          "construction is a finite-scenario instance of distributionally robust optimisation [22, 23] and of robust optimisation more "
          "generally [24], with the same seed used in every world so that differences reflect the world and not the draw."),
    ("h2", "Feasibility certificate", "sec:feas"),
    ("p", "When the goal is not reached, the Director needs to know whether the obstacle is financing availability or policy. The "
          "certificate begins with an exact result. Adding an amount <i>X</i> of free cash in week 1 lifts every weekly balance on every "
          "path by <i>X</i>, hence the trough by <i>X</i>. So P( <i>T</i> + <i>X</i> ≥ floor ) ≥ τ holds exactly when <i>X</i> is at "
          "least the τ-quantile of the required top-up:"),
    ("eq", "<i>X</i>* = <i>Q</i><sub>τ</sub>( max( 0, floor − <i>T<sub>n</sub></i> ) )", "eq:feas"),
    ("p", "No financing that arrives later, costs money, or is repaid inside the horizon can reach the goal with a smaller amount, so "
          "<i>X</i>* is a lower bound on the cash any plan must supply. It is compared with the over-borrowing cap 1.5 "
          "<i>S</i><super>0</super><sub>95</sub> and with the total funding that all eligible sources could provide. A set of probes then "
          "relaxes one limit at a time on the same scenarios (more packs inside the cap, free cash at the cap, every eligible source at "
          "once, the recommended plan drawn in week 1) and reports the resulting goal probability. The probes name the binding constraint "
          "(the cap, the eligible sources, the pack limit, draw timing, or repayment inside the horizon) and classify the case as "
          "reachable, limited by policy or sources, or not reachable with financing. They are diagnostics and are never offered as plans; "
          "the policy limits do not move."),
    ("p", "For the demonstration case the certificate shows that about USD 212,833 of cash in week 1 would suffice within the USD 354,755 "
          "cap, yet the best allowed plan reaches 18% and the same cash as free money would reach only 28%: factored invoices repay the "
          "factor and the loan matures inside the 13 weeks, so part of the cash leaves again before the low point."),
    ("h2", "Learning from outcomes under human control", "sec:learn"),
    ("p", "<b>Memory and attribution.</b> The Core stores each plan with its predicted goal probability and, later, the realised outcome, in "
          "a hash-chained case memory. An attribution step classifies a miss as collections timing, order slippage, cost overrun, funding "
          "too small, objective too narrow, or unexplained. Retrieval of similar past cases uses standardised Euclidean distance on a small "
          "feature vector, with each coordinate divided by its standard deviation across stored episodes."),
    ("p", "<b>Estimating a correction.</b> Observed on-time outcomes <i>y<sub>i</sub></i> for buyer <i>b</i> are modelled with the "
          "marginal on-time probability μ<sub><i>i</i></sub>(δ) = σ( logit <i>p<sub>i</sub></i> + δ ) · [ (1 − π) + π<i>m</i> ] (the "
          "slowdown state is marginalised out). The learner finds the maximum a posteriori shift under a zero-mean Gaussian prior of "
          "precision γ<sub><i>s</i></sub> = 1,"),
    ("eq", "δ<sub><i>b</i></sub>* = argmax<sub>δ</sub> { ∑<sub><i>i</i> ∈ <i>b</i></sub> [ <i>y<sub>i</sub></i> ln μ<sub><i>i</i></sub>(δ) + (1 − <i>y<sub>i</sub></i>) ln(1 − μ<sub><i>i</i></sub>(δ)) ] − ( γ<sub><i>s</i></sub> / 2 ) δ<super>2</super> }", "eq:map"),
    ("p", "by Newton iteration with analytic first and second derivatives, requiring at least 8 observations per buyer and clipping to ±3 "
          "logits. The order-shipment scale is a conjugate-style posterior mean with pseudo-count <i>n</i><sub>0</sub> = 10 at the prior "
          "scale <i>s</i><sub>0</sub>: <i>s</i> = ( shipped + <i>n</i><sub>0</sub><i>s</i><sub>0</sub> ) / ( ∑ <i>c<sub>i</sub></i> + "
          "<i>n</i><sub>0</sub> )."),
    ("p", "<b>Acceptance test.</b> A candidate is evaluated by leave-one-episode-out cross-validation [25]: fit on all other episodes and "
          "score the held-out episode by mean log-likelihood per observation, for both the candidate and the active parameters. With "
          "<i>K</i> episodes it is accepted only if the mean gain is at least 0.002 nats per observation, it wins on at least ceil(<i>K</i>/2) "
          "held-out episodes, and there are at least three episodes and 60 observations. Acceptance only produces a pending proposal; "
          "activating it is an L2 action that needs a named human, and every activation records who approved it and the evidence."),
    ("h2", "Executive Inbox routing", "sec:inbox"),
    ("p", "After each event (for example a cancelled order) the Core re-plans and decides whether the Director must be interrupted. An event "
          "is routed to the Director only if a reason exists: the plan in force has become unavailable; the recommended plan changes and the "
          "plan in force has lost more than 5 points of goal probability; the goal has become unreachable and the plan in force has fallen; "
          "or the first negative week has moved earlier. Otherwise it goes to a daily digest. Within the inbox, events are ordered by"),
    ("eq", "score = ( Δtrough / 1000 ) · certainty / max( 1, weeks to first negative week ) + 10 · 𝟙( plan in force loses ≥ 30 points )", "eq:inbox"),
    ("p", "where Δtrough is the base-case drop in the minimum closing balance and certainty is a source-specific constant. Priority is HIGH "
          "when four or fewer weeks remain or the plan loses 30 or more points. The rule is a transparent heuristic, not a fitted model; its "
          "quality is measured against a threshold baseline in Section [[sec:eval]]."),
    ("h2", "Financial-distress screening hint", "sec:distress"),
    ("p", "A logistic model on three ledger ratios is shipped as a coefficient file. For a company with DSO, DIO and gross margin "
          "<i>x</i><sub>1..3</sub> the score is computed as follows: winsorise each ratio at the training 1st and 99th percentiles; "
          "transform it with the signed logarithm τ(<i>x</i>) = sign(<i>x</i>) ln(1 + |<i>x</i>|); standardise with the training mean and "
          "standard deviation; and apply"),
    ("eq", "<i>z</i> = β<sub>0</sub> + ∑<sub><i>j</i>=1</sub><super>3</super> β<sub><i>j</i></sub> · ( τ( clip( <i>x<sub>j</sub></i> ) ) − μ<sub><i>j</i></sub> ) / σ<sub><i>j</i></sub>,&nbsp;&nbsp; <i>p</i> = σ(<i>z</i>)", "eq:distress"),
    ("p", "The contribution of each ratio to the log-odds is returned, as is a flag for any input outside the training range. The model "
          "follows the classical use of accounting ratios for failure prediction [26, 27] and is trained offline on the Polish Companies "
          "Bankruptcy data [28] for a one-year horizon. Its ROC-AUC is about 0.74 at one year and 0.59–0.64 at two to five years, against "
          "0.93–0.96 for a tree model on all 64 ratios; the output is therefore labelled a screening hint, is marked out of domain for the "
          "synthetic exporter, and states that it is not a credit decision."),
]
