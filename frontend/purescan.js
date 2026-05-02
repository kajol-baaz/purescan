const $particles = $(".particles");
if ($particles.length) {
    for (let i = 0; i < 25; i++) {
        const size = Math.random() * 4 + 2;
        $particles.append(
            $("<div></div>").addClass("particle").css({
                width: size + "px",
                height: size + "px",
                left: Math.random() * 100 + "%",
                bottom: Math.random() * 40 + "%",
                background: Math.random() > 0.5 ? "#00e5a0" : "#00bcd4",
                "--dur": (Math.random() * 2 + 2) + "s",
                "--delay": (Math.random() * 2) + "s",
            })
        );
    }
}

// ================================================================
// SPLASH EXIT  (purescan.html)
// ================================================================
const $splash = $("#splash");
if ($splash.length) {
    setTimeout(function () {
        $splash.css({ transition: "all 0.6s ease", opacity: "0", transform: "scale(1.05)" });
        setTimeout(function () {
            $splash.hide();
            $(".app").css({ opacity: "1", transition: "0.5s ease" });
        }, 600);
    }, 2200);
}
$(document).ready(function () {

    // ===== UTILITIES =====
    function scrollChat() {
        const chatbox = $("#chatbox");
        chatbox.scrollTop(chatbox.prop("scrollHeight"));
    }

    const API_BASE = window.location.origin;
    const minBudget = localStorage.getItem('userMinBudget') || "200";
    const maxBudget = localStorage.getItem('userMaxBudget') || "1000";

    $("#results").show(); // ensure visible

    $("#chatbox").append(`
    <div class="ai-msg">
        <p>👋 Hello! Welcome to <strong>PureScan</strong> 🌿</p>
        <p>💰 Budget: <strong>₹${minBudget} – ₹${maxBudget}</strong></p>
        <p>📸 Upload a product image <em>or</em> 💬 type a question below!</p>
        <p style="margin-top:6px;font-size:12px;color:#94a3b8;">
            Try: "show me juice options", "chips alternatives", "anti-dandruff shampoo"
        </p>
    </div>
`);


    // ===== BUDGET SCREEN =====
    $("#scan-screen-btn").on("click", function () {
        const min = ($("#budget-min").val() || "").trim();
        const max = ($("#budget-max").val() || "").trim();

        if (!min || !max) {
            alert("⚠ Enter both min & max budget");
            return;
        }

        if (Number(min) > Number(max)) {
            alert("⚠ Min cannot be greater than max");
            return;
        }

        localStorage.setItem("userMinBudget", min);
        localStorage.setItem("userMaxBudget", max);

        window.location.href = "ai-scan.html";
    });
    // when click on scan btn it will show budget screen
    $('.scan-btn').on('click', function () {
        $('#budget-screen').addClass('show');
    });
    $("svg").on("click", function () {
        $('#budget-screen').removeClass('show');
    });
    // ===== NAVIGATION =====
    $("#home-btn").on("click", function () {
        window.location.href = "purescan.html";
    });

    // ===== TRIGGER FILE INPUTS =====
    $('#galleryBtn').on('click', function () {
        $('#galleryInput').click();
    });

    $('#cameraBtn').on('click', function () {
        $('#cameraInput').click();
    });

    // ===== READ ALOUD =====
    let isSpeaking = false;

    $('#readAloudBtn').on('click', function () {
        const chatText = $('#chatbox').text().trim();

        if (chatText === "") {
            alert("📢 Nothing to read yet.");
            return;
        }

        // 🔴 IF SPEAKING → STOP
        if (isSpeaking) {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(chatText);
            utterance.rate = 0.95;

            utterance.onend = function () {
                isSpeaking = false;
                $("#readAloudBtn").text("🔊 Read Aloud");
            };

            window.speechSynthesis.speak(utterance);

            alert("🔊 Voice output started");
        }
    });

    // ===== HELPER: Build scan result HTML =====
    function buildScanHTML(res) {
        let html = `<b>${res.reply || "Scan Complete"}</b><br><br>`;

        // OCR Extracted Text
        if (res.extracted_text) {
            html += `<h4>📸 OCR Extracted Text</h4>`;
            html += `<div class="result-box ocr-box">${res.extracted_text}</div><hr>`;
        }

        // Ingredient Analysis
        if (Array.isArray(res.ingredients) && res.ingredients.length > 0) {
            html += `<h4></h4>`;
            res.ingredients.forEach(i => {
                const riskClass = (i.risk || "").toLowerCase();
                let riskBadge = `<span class="risk-badge risk-${riskClass}">${i.risk || "N/A"}</span>`;
                html += `
                    <div class="result-box ingredient-box">
                        <div class="result-header">
                            <b>${i.name || "N/A"}</b>
                            ${riskBadge}
                        </div>
                        <span class="decoded-name">${i.decoded || ""}</span>
                        <p class="result-desc">${i.description || ""}</p>
                    </div>
                `;
            });
            html += `<hr>`;
        }

        // Product Suggestions
        if (Array.isArray(res.product_suggestions) && res.product_suggestions.length > 0) {
            html += `<h4>🛒 Suggested Products</h4>`;
            res.product_suggestions.forEach(p => {
                html += `
                    <div class="result-box product-box">
                        <div class="result-header">
                            <b>${p.name || "N/A"}</b>
                            <span class="price-tag">₹${p.price || "N/A"}</span>
                        </div>
                        <div class="product-meta">
                            <span>⭐ ${p.rating || "N/A"}</span>
                            <span>🔗 ${p.review_source || "N/A"}</span>
                        </div>
                        <p class="result-desc">${p.description || ""}</p>
                        <p class="safety-note">⚠️ ${p.safety_note || "N/A"}</p>
                    </div>
                `;
            });
            html += `<hr>`;
        }

        // Food Alternatives
        if (Array.isArray(res.food_alternatives) && res.food_alternatives.length > 0) {
            html += `<h4>🍎 Healthy Alternatives</h4>`;
            res.food_alternatives.forEach(f => {
                html += `
                    <div class="result-box food-box">
                        <b>${f.name || "N/A"}</b><br>
                        👉 Try: ${f.alternative || "N/A"}<br>
                        <p class="result-desc">${f.description || "No description"}</p>
                    </div>
                `;
            });
            html += `<hr>`;
        }

        // Remedies
        if (Array.isArray(res.home_remedies) && res.home_remedies.length > 0) {
            html += `<h4>🌿 Home Remedies</h4>`;
            res.home_remedies.forEach(r => {
                html += `
                    <div class="result-box remedy-box">
                        <b>🌱 ${r.remedy || "N/A"}</b>
                        <span class="remedy-issue">${r.issue || ""}</span>
                        <p class="result-desc">${r.description || ""}</p>
                    </div>
                `;
            });
        }

        return html;
    }

    // ===== HELPER: Build chat result HTML =====
    function buildChatHTML(res) {
        let html = `<b>${res.reply || "Results 😊"}</b><br><br>`;

        // Products
        if (Array.isArray(res.products) && res.products.length > 0) {
            html += `<h4>🛒 Market Available Products</h4>`;
            res.products.forEach(p => {
                html += `
                    <div class="result-box product-box">
                        <div class="result-header">
                            <b>${p.name || "N/A"}</b>
                            <span class="price-tag">₹${p.price || "N/A"}</span>
                        </div>
                        <div class="product-meta">
                            <span>⭐ ${p.rating || "N/A"}</span>
                            <span>🔗 ${p.review_source || "N/A"}</span>
                        </div>
                        <p class="result-desc">${p.description || "No description available"}</p>
                    </div>
                `;
            });
            html += `<hr>`;
        }

        // Food Suggestions
        if (Array.isArray(res.food_suggestions) && res.food_suggestions.length > 0) {
            html += `<h4>🥘 Healthy Food Options</h4>`;
            res.food_suggestions.forEach(food => {
                html += `
                    <div class="result-box food-box">
                        <div class="result-header">
                            <b>${food.name || "N/A"}</b>
                            <span class="price-tag">₹${food.price || "N/A"}</span>
                        </div>
                        <p class="result-desc">${food.description || "No description available"}</p>
                    </div>
                `;
            });
            html += `<hr>`;
        }

        // Remedies
        if (Array.isArray(res.home_remedies) && res.home_remedies.length > 0) {
            html += `<h4>🌿 Home Remedies</h4>`;
            res.home_remedies.forEach(r => {
                html += `
                    <div class="result-box remedy-box">
                        <b>🌱 ${r.remedy || r.remedy_name || "N/A"}</b>
                        <span class="remedy-issue">${r.issue || ""}</span>
                        <p class="result-desc">${r.description || "No description available"}</p>
                    </div>
                `;
            });
        }

        // Empty State
        if (
            (!res.products || res.products.length === 0) &&
            (!res.food_suggestions || res.food_suggestions.length === 0) &&
            (!res.home_remedies || res.home_remedies.length === 0)
        ) {
            html += `<div class="empty-state">❌ No matching results found. Try different keywords!</div>`;
        }

        return html;
    }

    // ===== IMAGE SCAN =====
    $('#galleryInput, #cameraInput').on('change', function () {
        localStorage.removeItem("lastIngredients");

        const file = this.files[0];
        if (!file) return;

        $('#results').show();

        const imageURL = URL.createObjectURL(file);

        $('#chatbox').append(`
            <div class="user-msg image-msg">
                <img src="${imageURL}" class="scan-preview">
            </div>
        `);

        setTimeout(scrollChat, 100);

        const loadingMsg = $(`
            <div class="ai-msg loading-msg">
                <div class="loading-dots">
                    <span></span><span></span><span></span>
                </div>
                <span>Analyzing your product... 🧪</span>
            </div>
        `);
        $('#chatbox').append(loadingMsg);
        scrollChat();

        const formData = new FormData();
        formData.append("file", file);
        formData.append("min_budget", Number(minBudget));
        formData.append("max_budget", Number(maxBudget));

        $.ajax({
            url: `${API_BASE}/purescan`,
            type: "POST",
            data: formData,
            processData: false,
            contentType: false,

            success: function (res) {
                console.log("SCAN RESPONSE:", res);
                loadingMsg.remove();

                if (!res) {
                    $('#chatbox').append(`<div class="ai-msg">❌ Empty response from server</div>`);
                    return;
                }

                let html = buildScanHTML(res);
                let msg = $('<div class="ai-msg"></div>');
                msg.html(html);
                $('#chatbox').append(msg);
                scrollChat();
            },

            error: function (xhr, status, error) {
                console.log("SCAN ERROR:", xhr.responseText);
                loadingMsg.remove();
                $('#chatbox').append(`<div class="ai-msg error-msg">❌ Scan failed. Please try again with a clearer image.</div>`);
                scrollChat();
            }
        });

        // Reset file input so same file can be re-selected
        $(this).val('');
    });

    // ===== CHAT SEND =====
    function sendChatMessage() {
        const message = $('#chatInput').val().trim();
        if (!message) return;

        $("#results").show();
        $('#chatInput').val('');

        $('#chatbox').append(`<div class="user-msg">💬 ${message}</div>`);
        scrollChat();

        const loadingMsg = $(`
            <div class="ai-msg loading-msg">
                <div class="loading-dots">
                    <span></span><span></span><span></span>
                </div>
                <span>Thinking...</span>
            </div>
        `);
        $('#chatbox').append(loadingMsg);
        scrollChat();

        $.ajax({
            url: `${API_BASE}/chat`,
            type: "POST",
            contentType: "application/json",
            data: JSON.stringify({
                message: message,
                min_budget: localStorage.getItem("userMinBudget") || 0,
                max_budget: localStorage.getItem("userMaxBudget") || 999999
            }),

            success: function (res) {
                loadingMsg.remove();

                let html = buildChatHTML(res);
                $("#chatbox").append(`<div class="ai-msg">${html}</div>`);
                scrollChat();
            },

            error: function () {
                loadingMsg.remove();
                $('#chatbox').append(`<div class="ai-msg error-msg">❌ Request failed. Please try again.</div>`);
                scrollChat();
            }
        });
    }

    $('#sendChatBtn').on('click', sendChatMessage);

    // Enter key to send chat
    $('#chatInput').on('keypress', function (e) {
        if (e.which === 13) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    // ===== SCROLL ANIMATIONS (Landing Page) =====
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('show');
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));
});
