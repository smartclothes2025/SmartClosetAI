// src/pages/Assistant.jsx
import React, { useEffect, useRef, useState } from "react";
import PropTypes from "prop-types";
import Layout from "../components/Layout";

// ✅ 新增：取得 Token 的輔助函式
function getToken() {
  return localStorage.getItem("token") || "";
}

export default function Assistant({ theme, setTheme }) {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: "assistant",
      text: "嗨！我是你的穿搭小助手，有什麼穿搭建議都歡迎詢問我喔",
    },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [sending, setSending] = useState(false);

  const scrollRef = useRef(null);
  const nextIdRef = useRef(2);

  // inline height for .assistant-card (px)
  const [cardHeightPx, setCardHeightPx] = useState(null);

  // === 計算卡片高度（桌機 vs 手機） ===
  function computeCardHeightPx() {
    const rootFontSize =
      parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    const isMobile = window.matchMedia("(max-width: 768px)").matches;

    // header 元素高度（桌機用）
    const headerEl = document.querySelector("header");
    const headerH = headerEl
      ? headerEl.getBoundingClientRect().height
      : 4 * rootFontSize; // fallback 4rem

    // 手機額外空間：10em -> px
    const mobileExtraPx = 10 * rootFontSize;

    const vh = window.innerHeight;
    const final = isMobile
      ? Math.max(200, Math.floor(vh - mobileExtraPx))
      : Math.max(200, Math.floor(vh - headerH));
    return final;
  }

  // 初始化並監聽 resize/orientationchange & header size change
  useEffect(() => {
    function update() {
      setCardHeightPx(computeCardHeightPx());
    }
    update();

    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);

    // 監聽 header 高度變化（若 header 存在）
    let ro;
    const headerEl = document.querySelector("header");
    if (headerEl && typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => update());
      ro.observe(headerEl);
    }

    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
      if (ro && headerEl) ro.disconnect();
    };
  }, []);

  // 將 body overflow 設為 hidden（避免整頁滾動），離開時還原
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  // 當 messages / isTyping 變動時，滾動訊息區到底（只滾訊息區）
  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    });
    return () => cancelAnimationFrame(raf);
  }, [messages, isTyping]);

  function addMessage(role, text) {
    setMessages((m) => [...m, { id: nextIdRef.current++, role, text }]);
  }

  async function handleSend(e) {
    e?.preventDefault();
    const txt = input.trim();
    if (!txt || sending) return;
    setSending(true);
    addMessage("user", txt);
    setInput("");

    setIsTyping(true);

    try {
      // ✅ 修改：加入 Authorization header
      const token = getToken();
      if (!token) {
        throw new Error("未找到登入 Token，請先登入");
      }

      const res = await fetch("http://127.0.0.1:8000/api/v1/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,  // ✅ 加入這行
        },
        body: JSON.stringify({ user_input: txt }),
      });

      // 檢查 HTTP 響應狀態
      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`伺服器回應錯誤: ${res.status} ${res.statusText} - ${errorText}`);
      }

      const data = await res.json();
      console.log("前端收到的數據:", data);

      if (data.type === "image") {
        if (data.text) {
          addMessage("assistant", data.text);
        }
        if (data.url) {
          addMessage("assistant", (
            <img
              src={data.url}
              alt="穿搭建議"
              className="mt-2 w-full max-w-2xl rounded-xl shadow-md"
            />
          ));
        } else {
          addMessage("assistant", "⚠️ 圖片回覆缺少圖片 URL。");
        }
      } else if (data.type === "text") {
        if (data.text) {
          addMessage("assistant", data.text);
        } else {
          addMessage("assistant", "⚠️ 文字回覆缺少內容。");
        }
      } else if (data.error) {
        addMessage("assistant", `⚠️ 錯誤：${data.error}`);
      } else {
        addMessage("assistant", "⚠️ 後端沒有回覆內容（未知格式）。");
      }

    } catch (err) {
      addMessage("assistant", `🚨 伺服器連線或資料處理失敗：${err.message}`);
    } finally {
      setIsTyping(false);
      setSending(false);
    }
  }

  const quickPrompts = ["推薦今日穿搭", "正式場合穿搭建議"];

  return (
    <Layout title="穿搭小助手">
      <div className="page-wrapper">
        <div className="max-w-5xl mx-auto mt-2">
          <div
            className="assistant-card bg-white rounded-2xl shadow-sm overflow-hidden flex flex-col"
            style={cardHeightPx ? { height: `${cardHeightPx}px` } : undefined}
          >
            {/* 訊息區 */}
            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto p-4"
              aria-live="polite"
            >
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`mb-4 flex ${
                    m.role === "assistant" ? "items-start" : "justify-end"
                  }`}
                >
                  {m.role === "assistant" && (
                    <div className="flex-shrink-0 mr-3">
                      <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-bold">
                        🤖
                      </div>
                    </div>
                  )}

                  <div>
                    <div
                      className={`px-4 py-2 max-w-[70ch] break-words ${
                        m.role === "assistant"
                          ? "bg-gray-100 text-gray-800 rounded-xl rounded-tl-none"
                          : "bg-indigo-600 text-white rounded-xl rounded-tr-none"
                      }`}
                    >
                      {typeof m.text === "string" ? m.text : m.text}
                    </div>
                  </div>

                  {m.role === "user" && (
                    <div className="flex-shrink-0 ml-3">
                      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-gray-700 font-medium">
                        U
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {isTyping && (
                <div className="mb-4 flex items-start">
                  <div className="flex-shrink-0 mr-3">
                    <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-bold">
                      🤖
                    </div>
                  </div>
                  <div className="bg-gray-100 rounded-xl rounded-tl-none px-4 py-2">
                    <div className="flex items-center gap-1">
                      <span className="dot" style={{ animationDelay: "0ms" }} />
                      <span
                        className="dot"
                        style={{ animationDelay: "120ms" }}
                      />
                      <span
                        className="dot"
                        style={{ animationDelay: "240ms" }}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 輸入區*/}
            <div className="border-t px-4 py-4 bg-white flex-shrink-0">
              <div className="flex gap-2 mb-3 flex-wrap">
                {quickPrompts.map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setInput(q);
                      // 使用 setTimeout 確保 input 已更新
                      setTimeout(() => {
                        handleSend(null);
                      }, 0);
                    }}
                    className="px-3 py-1 rounded-full border text-sm"
                  >
                    {q}
                  </button>
                ))}
              </div>

              <form onSubmit={handleSend} className="flex items-center gap-3">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) handleSend(e);
                  }}
                  placeholder="在這裡輸入，你可以問各種穿搭建議"
                  className="flex-1 border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
                <button
                  type="submit"
                  className="bg-indigo-600 text-white px-4 py-3 rounded-xl"
                  disabled={sending}
                >
                  {sending ? "傳送中…" : "送出"}
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}

Assistant.propTypes = {
  theme: PropTypes.string.isRequired,
  setTheme: PropTypes.func.isRequired,
};
