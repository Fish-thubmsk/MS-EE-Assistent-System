const subjectSelect = document.getElementById("subjectSelect");
const typeSelect = document.getElementById("typeSelect");
const yearSelect = document.getElementById("yearSelect");
const nextBtn = document.getElementById("nextBtn");
const questionCard = document.getElementById("questionCard");
const meta = document.getElementById("meta");

let currentSubject = "";
let currentType = "";
let currentYear = "";
let selectedOptionKeys = new Set();

async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
}

function optionBlock(label, text) {
    if (!text) return "";
    return `
        <div class="option">
            <div class="badge">${label}</div>
            <div class="option-text"></div>
        </div>
    `;
}

function renderQuestion(q) {
    const isEnglishReadingLike = currentSubject === "english" && (currentType === "reading" || currentType === "new_type" || currentType === "cloze");
    const itemNo = q.item_no || q.sub_question_number || q.question_number || "";
    const stem = isEnglishReadingLike
        ? (itemNo ? `第 ${itemNo} 题` : "本篇小题")
        : (q.stem || q.question || q.sub_question || q.prompt || q.english_text || "（无题干）");
    const article = q.article || q.material || "";
    const answer = q.answer || "";

    questionCard.innerHTML = "";
    selectedOptionKeys = new Set();

    if (article) {
        const articleEl = document.createElement("div");
        articleEl.className = "q-article";
        articleEl.textContent = article;
        questionCard.appendChild(articleEl);
    }

    const titleEl = document.createElement("p");
    titleEl.className = "q-title";
    titleEl.textContent = stem;
    questionCard.appendChild(titleEl);

    const optionsEl = document.createElement("div");
    optionsEl.className = "options";
    const entries = [["A", q.optionA], ["B", q.optionB], ["C", q.optionC], ["D", q.optionD]];
    for (const [label, text] of entries) {
        if (!text) continue;
        const item = document.createElement("div");
        item.className = "option";
        item.dataset.key = label;
        const badge = document.createElement("div");
        badge.className = "badge";
        badge.textContent = label;
        const textEl = document.createElement("div");
        textEl.className = "option-text";
        textEl.textContent = text;
        item.appendChild(badge);
        item.appendChild(textEl);
        item.addEventListener("click", () => handleOptionToggle(item));
        optionsEl.appendChild(item);
    }
    if (optionsEl.children.length > 0) {
        questionCard.appendChild(optionsEl);

        const panel = document.createElement("div");
        panel.className = "judge-panel";
        const submitBtn = document.createElement("button");
        submitBtn.className = "btn-secondary";
        submitBtn.textContent = "提交答案";
        submitBtn.addEventListener("click", () => handleSubmit(answer));
        panel.appendChild(submitBtn);
        questionCard.appendChild(panel);
    }

    if (answer) {
        const answerEl = document.createElement("div");
        answerEl.className = "answer";
        answerEl.id = "answerBox";
        answerEl.style.display = "none";
        answerEl.textContent = `参考答案：${answer}`;
        questionCard.appendChild(answerEl);
    }

    if (window.MathJax && window.MathJax.typesetPromise) {
        window.MathJax.typesetPromise([questionCard]).catch(() => {});
    }
}

function normalizeAnswer(answer) {
    return Array.from(new Set(String(answer || "").toUpperCase().replace(/[^A-D]/g, "").split(""))).sort().join("");
}

function handleOptionToggle(optionEl) {
    if (optionEl.dataset.locked === "1") return;
    const key = optionEl.dataset.key || "";
    const isMultiple = currentType === "multiple";
    if (isMultiple) {
        if (selectedOptionKeys.has(key)) {
            selectedOptionKeys.delete(key);
            optionEl.classList.remove("selected");
        } else {
            selectedOptionKeys.add(key);
            optionEl.classList.add("selected");
        }
    } else {
        selectedOptionKeys = new Set([key]);
        const all = questionCard.querySelectorAll(".option");
        all.forEach(el => el.classList.remove("selected"));
        optionEl.classList.add("selected");
    }
}

function handleSubmit(answer) {
    const all = questionCard.querySelectorAll(".option");
    if (all.length === 0) return;
    if (selectedOptionKeys.size === 0) return;

    const picked = Array.from(selectedOptionKeys).sort().join("");
    const std = normalizeAnswer(answer);

    all.forEach(el => {
        el.classList.remove("correct", "wrong");
        el.dataset.locked = "1";
        el.style.pointerEvents = "none";
        const k = el.dataset.key || "";
        if (std.includes(k)) {
            el.classList.add("correct");
        } else if (selectedOptionKeys.has(k)) {
            el.classList.add("wrong");
        }
    });

    const answerBox = document.getElementById("answerBox");
    if (answerBox) {
        const ok = picked === std;
        answerBox.style.display = "block";
        answerBox.textContent = `参考答案：${std || "（无）"} ｜ 你的选择：${picked} ｜ ${ok ? "回答正确 ✅" : "回答错误 ❌"}`;
    }
}

async function loadSubjects() {
    const subjects = await fetchJson("/api/subjects");
    subjectSelect.innerHTML = subjects
        .map(s => `<option value="${s.id}">${s.icon} ${s.name}</option>`)
        .join("");
    currentSubject = subjectSelect.value;
}

async function loadTypes() {
    const types = await fetchJson(`/api/subject/${currentSubject}/types`);
    typeSelect.innerHTML = types
        .map(t => `<option value="${t.id}">${t.name}</option>`)
        .join("");
    currentType = typeSelect.value;
}

async function loadYears() {
    const years = await fetchJson(`/api/years/${currentSubject}`);
    yearSelect.innerHTML = `<option value="">全部年份</option>` + years.map(y => `<option value="${y}">${y}</option>`).join("");
    currentYear = "";
}

async function nextQuestion() {
    try {
        const qs = currentYear ? `?year=${encodeURIComponent(currentYear)}` : "";
        const data = await fetchJson(`/api/question/${currentSubject}/${currentType}${qs}`);
        const q = data.questions?.[0];
        if (!q) {
            questionCard.innerHTML = `<div class="placeholder">该题型暂无数据。</div>`;
            meta.textContent = `题库总量：${data.total || 0}`;
            return;
        }
        renderQuestion(q);
        const ytxt = currentYear ? ` ｜ 年份：${currentYear}` : "";
        meta.textContent = `科目：${subjectSelect.options[subjectSelect.selectedIndex].text} ｜ 题型：${typeSelect.options[typeSelect.selectedIndex].text}${ytxt} ｜ 题库总量：${data.total}`;
    } catch (err) {
        questionCard.innerHTML = `<div class="placeholder">加载失败：${String(err)}</div>`;
    }
}

subjectSelect.addEventListener("change", async () => {
    currentSubject = subjectSelect.value;
    await loadTypes();
    await loadYears();
    await nextQuestion();
});

typeSelect.addEventListener("change", async () => {
    currentType = typeSelect.value;
    await nextQuestion();
});

yearSelect.addEventListener("change", async () => {
    currentYear = yearSelect.value;
    await nextQuestion();
});

nextBtn.addEventListener("click", nextQuestion);

(async function init() {
    await loadSubjects();
    await loadTypes();
    await loadYears();
    await nextQuestion();
})();
