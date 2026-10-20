import type { Bi, ContractDocument, ContractLang } from "./api";

/** The draft laid out like the Word file: title block, parties, numbered articles, schedules, signature blocks. */
export function ContractPreview({ doc, lang }: { doc: ContractDocument; lang: ContractLang }) {
  const bi = lang === "bilingual";
  const one = (x: Bi | string) => (typeof x === "string" ? x : lang === "vi" ? x.vi : x.en);
  const cell = (x: Bi | string) => (typeof x === "string" ? x : bi ? (x.vi === x.en ? x.vi : `${x.vi} / ${x.en}`) : one(x));
  const money = (x: Bi | string) => (typeof x === "string" ? x : lang === "vi" ? x.vi : x.en);
  const Para = ({ no, text }: { no: string; text: Bi }) =>
    bi ? (
      <div className="cp-bi">
        <p><b>{no}</b> {text.vi}</p>
        <p lang="en"><b>{no}</b> <i>{text.en}</i></p>
      </div>
    ) : (
      <p className="cp-clause"><b>{no}</b><span>{one(text)}</span></p>
    );
  const Heading = ({ vi, en }: { vi: string; en: string }) =>
    bi ? (
      <div className="cp-bi cp-h"><h4>{vi}</h4><h4 lang="en"><i>{en}</i></h4></div>
    ) : (
      <h4 className="cp-h">{lang === "vi" ? vi : en}</h4>
    );

  return (
    <article className="contract-preview" tabIndex={0} aria-label={doc.title.en} lang={lang === "en" ? "en" : "vi"}>
      <p className="cp-notice">{bi ? `${doc.notice.vi} ${doc.notice.en}` : one(doc.notice)}</p>
      {lang !== "en" && (
        <div className="cp-motto">
          <b>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</b>
          <b>Độc lập - Tự do - Hạnh phúc</b>
        </div>
      )}
      <h3 className="cp-title">{bi ? doc.title.vi : one(doc.title)}</h3>
      {bi && <p className="cp-subtitle" lang="en">{doc.title.en}</p>}
      <p className="cp-meta">{bi ? doc.meta.vi : one(doc.meta)}</p>

      <Heading vi="CÁC BÊN" en="THE PARTIES" />
      <div className="cp-parties">
        {doc.parties.map((p, i) => (
          <table key={i} className="cp-table">
            <caption>{cell(p.role)}: <b>{p.name}</b></caption>
            <tbody>
              {p.rows.map(([k, v], j) => (
                <tr key={j}><th scope="row">{cell(k)}</th><td className={v === "[●]" ? "cp-todo" : ""}>{v}</td></tr>
              ))}
            </tbody>
          </table>
        ))}
      </div>

      <Heading vi="XÉT RẰNG" en="RECITALS" />
      {doc.recitals.map((r, i) => <Para key={i} no={`(${String.fromCharCode(65 + i)})`} text={r} />)}

      {doc.articles.map((a) => (
        <section key={a.no}>
          <Heading vi={`ĐIỀU ${a.no}. ${a.title.vi}`} en={`ARTICLE ${a.no}. ${a.title.en}`} />
          {a.clauses.map((c) => <Para key={c.no} no={c.no} text={c.text} />)}
        </section>
      ))}

      <div className="cp-signs">
        {doc.signatures.map((s, i) => (
          <div key={i}>
            <b>{cell(s.role)}</b>
            <span>{s.name}</span>
            <span className="cp-line" />
            <span>{s.person || "[●]"}{s.title ? `, ${s.title}` : ""}</span>
            <span className="cp-unsigned">{bi ? "CHƯA KÝ / NOT SIGNED" : lang === "vi" ? "CHƯA KÝ" : "NOT SIGNED"}</span>
          </div>
        ))}
      </div>

      {doc.schedules.map((s) => (
        <section key={s.no} className="cp-schedule">
          <Heading vi={`PHỤ LỤC ${s.no}. ${s.title.vi}`} en={`SCHEDULE ${s.no}. ${s.title.en}`} />
          {s.table && (
            <div className="scroll" tabIndex={0} role="region" aria-label={s.title.en}>
              <table className="cp-table cp-grid">
                <thead><tr>{s.table.header.map((h, i) => <th key={i} scope="col">{cell(h)}</th>)}</tr></thead>
                <tbody>
                  {s.table.rows.map((r, i) => (
                    <tr key={i}>{r.map((v, j) => <td key={j} className={j === 2 || j === 3 ? "num" : ""}>{j === 3 ? money(v) : cell(v)}</td>)}</tr>
                  ))}
                  <tr className="cp-total">
                    <td colSpan={2}>{cell(s.table.total[0])}</td>
                    <td className="num">{cell(s.table.total[1])}</td>
                    <td className="num">{money(s.table.total[2])}</td>
                    <td />
                  </tr>
                </tbody>
              </table>
            </div>
          )}
          {(s.items || []).map((it, i) => <Para key={i} no={`${i + 1}.`} text={it} />)}
        </section>
      ))}
    </article>
  );
}
