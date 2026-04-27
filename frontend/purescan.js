$(document).ready(function () {

    const $splash = $("#splash");
    const $app = $(".app");
    const $particles = $(".particles");

    // -----------------------------
    // 1. CREATE PARTICLES
    // -----------------------------
    if ($particles.length) {

        for (let i = 0; i < 25; i++) {

            const size = Math.random() * 4 + 2;

            const $particle = $("<div></div>").addClass("particle");

            $particle.css({
                width: size + "px",
                height: size + "px",
                left: Math.random() * 100 + "%",
                bottom: Math.random() * 40 + "%",
                background: Math.random() > 0.5 ? "#00e5a0" : "#00bcd4",
                "--dur": (Math.random() * 2 + 2) + "s",
                "--delay": (Math.random() * 2) + "s"
            });

            $particles.append($particle);
        }
    }

    // -----------------------------
    // 2. SPLASH EXIT ANIMATION
    // -----------------------------
    setTimeout(function () {

        $splash.css({
            transition: "all 0.6s ease",
            opacity: "0",
            transform: "scale(1.05)"
        });

        // remove after fade
        setTimeout(function () {
            $splash.hide();

            $app.css({
                opacity: "1",
                transition: "0.5s ease"
            });

        }, 600);

    }, 2200);

});

$(document).ready(function () {

    // ===== SCROLL FUNCTION =====
    function scrollChat() {
        const chatbox = $("#chatbox");
        chatbox.scrollTop(chatbox.prop("scrollHeight"));
    }

    // ===== WELCOME MESSAGE =====
    const minBudget = localStorage.getItem('userMinBudget') || "200";
    const maxBudget = localStorage.getItem('userMaxBudget') || "1000";

    $('#wellcome').append(`
        <div class="flex justify-start mb-4 mt-4 ml-4">
            <div class="ai-msg">
                <p>👋 Hello! Welcome to <strong>PureScan</strong> 🌿</p>
                <p>💰 Budget: <strong>₹${minBudget} - ₹${maxBudget}</strong></p>
                <p>📸 Upload a product or 💬 ask for suggestions!</p>
            </div>
        </div>
    `);

    scrollChat();

    // ===== SAVE BUDGET =====
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

    $('.scan-btn').on('click', function () {
        $('#budget-screen').addClass('show');
    });

    // ===== NAVIGATION =====
    $("#home-btn").on("click", function () {
        window.location.href = "purescan.html";
    });

    // ===== TRIGGER INPUTS =====
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
            isSpeaking = false;

            $("#readAloudBtn").text("🔊 Read Aloud");

            alert("🛑 Voice output stopped");
            return;
        }

        // 🟢 START SPEAKING
        if ('speechSynthesis' in window) {

            isSpeaking = true;
            $("#readAloudBtn").text("⏹ Stop Speaking");

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

    // ========= SCAN =========
    $('#galleryInput, #cameraInput').on('change', function () {

        localStorage.removeItem("lastIngredients");

        const file = this.files[0];
        if (!file) return;

        $('#results').show();

        const imageURL = URL.createObjectURL(file);

        $('#chatbox').append(`
            <div class="flex justify-end mb-3">
                <img src="${imageURL}" class="w-32 rounded-xl border">
            </div>
        `);

        setTimeout(scrollChat, 100);

        const loadingMsg = $('<div class="ai-msg"> Analyzing... 🧪</div>');
        $('#chatbox').append(loadingMsg);

        const formData = new FormData();
        formData.append("file", file);

        const minBudget = localStorage.getItem("userMinBudget") || "0";
        const maxBudget = localStorage.getItem("userMaxBudget") || "10000";

        formData.append("min_budget", Number(minBudget));
        formData.append("max_budget", Number(maxBudget));

        $.ajax({
            url: "http://127.0.0.1:8000/purescan",
            type: "POST", data: formData,
            processData: false,
            contentType: false,

            success: function (res) {

                console.log("SCAN RESPONSE:", res);

                if (loadingMsg) {
                    loadingMsg.remove();
                }

                if (!res) {
                    $('#chatbox').append(`<div class="ai-msg">❌ Empty response</div>`);
                    return;
                }

                let html = `<b>${res.reply || "Scan Complete"}</b><br><br>`;

                // ================= RAW OCR OUTPUT FIRST =================
                if (res.extracted_text) {

                    html += `<h4>📸 OCR Extracted Text</h4>`;

                    html += `
                <div class="ingredient-box" style="border-left:3px solid #9C27B0;">
                    ${res.extracted_text}
                </div>
                <hr>
            `;
                }


                // ================= INGREDIENT ANALYSIS =================
                if (Array.isArray(res.ingredients) && res.ingredients.length > 0) {

                    html += `<h4>🧪 Ingredient & Risk Analysis</h4>`;

                    res.ingredients.forEach(i => {
                        html += `
                    <div class="ingredient-box">
                        <b>${i.name || "N/A"}</b><br>
                        Risk: ${i.risk || "N/A"}<br>
                        ${i.description || ""}
                    </div>
        `;
                    });

                    html += `<hr>`;
                }



                // ================= PRODUCTS =================
                if (Array.isArray(res.product_suggestions) && res.product_suggestions.length > 0) {

                    html += `<h4>🛒 Products</h4>`;

                    res.product_suggestions.forEach(p => {
                        html += `
                <div class="product-box">
                    <b>${p.name || "N/A"}</b> - ₹${p.price || "N/A"}<br>
                    ⭐ Rating: ${p.rating || "N/A"}<br>
                    🔗 Review: ${p.review_source || "N/A"}<br>
                    ⚠ ${p.safety_note || "N/A"}<br>
                    📝 ${p.description || ""}
                </div>
            `;
                    });

                    html += `<hr>`;
                }

                // ================= FOOD =================
                if (Array.isArray(res.food_alternatives) && res.food_alternatives.length > 0) {

                    html += `<h4>🍎 Food Alternatives</h4>`;

                    res.food_alternatives.forEach(f => {
                        html += `
                <div class="food-box">
                    <b>${f.name || "N/A"}</b><br>
                    👉 Alternative: ${f.alternative || "N/A"}<br>
                    📝 ${f.description || "No description"}
                </div>
            `;
                    });

                    html += `<hr>`;
                }

                // ================= REMEDIES =================
                if (Array.isArray(res.home_remedies) && res.home_remedies.length > 0) {

                    html += `<h4>🌿 Remedies</h4>`;

                    res.home_remedies.forEach(r => {
                        html += `
                <div class="remedy-box">
                    🌱 <b>${r.remedy || "N/A"}</b><br>
                    ${r.description || ""}
                </div>
            `;
                    });

                    html += `<hr>`;
                }

                // ✅ IMPORTANT FIX (safe render)
                let msg = $('<div class="ai-msg"></div>');
                msg.html(html);
                $('#chatbox').append(msg);

                scrollChat();
            },

            error: function (xhr, status, error) {
                console.log("SCAN ERROR:", xhr.responseText);
                if (loadingMsg) loadingMsg.remove();
                $('#chatbox').append(`<div class="ai-msg">❌ Scan failed</div>`);
            }
        });
    });

    // ===== CHAT BUTTON =====
    $(document).ready(function () {

        function scrollChat() {
            const chatbox = $("#chatbox");
            chatbox.scrollTop(chatbox.prop("scrollHeight"));
        }

        // ================= FOOD DETECTION =================
        function isFoodQuery(text) {
            const foodKeywords = [
                "food", "eat", "meal", "diet", "recipe", "snack",
                "chips", "coconut water", "juice", "drink",
                "chana", "makhana", "breakfast", "lunch", "dinner"
            ];

            text = text.toLowerCase();

            return foodKeywords.some(k => text.includes(k));
        }

        $(document).ready(function () {

            function scrollChat() {
                const chatbox = $("#chatbox");
                chatbox.scrollTop(chatbox.prop("scrollHeight"));
            }

            function isFoodQuery(text) {
                const foodKeywords = [
                    "food", "eat", "drink", "snack", "chips",
                    "coconut water", "juice", "makhana", "chana", "juice", "diet"
                ];
                text = text.toLowerCase();
                return foodKeywords.some(k => text.includes(k));
            }

            $('#sendChatBtn').on('click', function () {

                const message = $('#chatInput').val().trim();
                if (!message) return;
                $("#results").show();
                $('#chatInput').val('');

                $('#chatbox').append(`<div class="user-msg">💬 ${message}</div>`);

                scrollChat();

                // ❌ ONLY ONE API (IMPORTANT FIX)
                $.ajax({
                    url: "http://127.0.0.1:8000/chat",
                    type: "POST",
                    contentType: "application/json",
                    data: JSON.stringify({
                        message: message,
                        min_budget: localStorage.getItem("userMinBudget") || 0,
                        max_budget: localStorage.getItem("userMaxBudget") || 999999
                    }),

                    success: function (res) {
                        let html = `<b>${res.reply || "Results 😊"}</b><br><br>`;

                        // ================= PRODUCTS =================
                        if (Array.isArray(res.products) && res.products.length > 0) {

                            html += `<h4>🛒 Products</h4>`;

                            res.products.forEach(product => {

                                const name = product.name || "N/A";
                                const price = product.price !== undefined ? `₹${product.price}` : "N/A";
                                const description = product.description || "No description available";

                                html += `
            <div>
                <b>${name}</b> - ${price}<br>
                ${description}
            </div><hr>
        `;
                            });
                        }

                        // ================= FOOD =================
                        if (Array.isArray(res.food_suggestions) && res.food_suggestions.length > 0) {

                            html += `<h4>Market avalible option for food🥘</h4>`;

                            res.food_suggestions.forEach(food => {

                                const name = food.name || "N/A";
                                const price = food.price || "N/A";
                                const description = food.description || "No description available";

                                html += `
            <div>
                <b>${name}</b><br>
                🍃 price: ${price}<br>
                ${description}
            </div><hr>
        `;
                            });
                        }

                        // ================= REMEDIES =================
                        if (Array.isArray(res.home_remedies) && res.home_remedies.length > 0) {

                            html += `<h4>🌿 Remedies</h4>`;

                            res.home_remedies.forEach(remedyItem => {

                                const remedyName = remedyItem.remedy || remedyItem.remedy_name || "N/A";
                                const description = remedyItem.description || "No description available";

                                html += `
            <div>
                🌱 <b>${remedyName}</b><br>
                ${description}
            </div><hr>
        `;
                            });
                        }

                        // ================= EMPTY STATE =================
                        if (
                            (!res.products || res.products.length === 0) &&
                            (!res.food_suggestions || res.food_suggestions.length === 0) &&
                            (!res.home_remedies || res.home_remedies.length === 0)
                        ) {
                            html += `<div>❌ No matching results found</div>`;
                        }

                        $("#chatbox").append(`<div class="ai-msg">${html}</div>`);
                        scrollChat();
                    },

                    error: function () {
                        $('#chatbox').append(`<div class="ai-msg">❌ Request failed</div>`);
                    }
                });
            });
        });
    });
});