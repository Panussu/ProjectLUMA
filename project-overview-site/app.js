// Project LUMA Documentation Web Page - Interactive Logic (Thai Edition)
(() => {
  "use strict";

  // 1. ตรวจจับการเลื่อนหน้าจอเพื่อไฮไลต์เมนูข้าง (Active Navigation)
  const sections = document.querySelectorAll(".doc-section");
  const navLinks = document.querySelectorAll(".nav-link");

  const observerOptions = {
    root: null,
    rootMargin: "-80px 0px -60% 0px",
    threshold: 0
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const id = entry.target.getAttribute("id");
        navLinks.forEach((link) => {
          const href = link.getAttribute("href");
          if (href === `#${id}`) {
            link.classList.add("active");
          } else {
            link.classList.remove("active");
          }
        });
      }
    });
  }, observerOptions);

  sections.forEach((section) => observer.observe(section));

  // 2. ระบบค้นหาแบบเรียลไทม์ (Quick Search) รองรับทั้งภาษาไทยและอังกฤษ
  const searchInput = document.getElementById("quickSearch");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      const term = e.target.value.toLowerCase().trim();
      const searchableCards = document.querySelectorAll(".step-box, .code-explain-card, .gallery-item, .trouble-card, .analogy-card, .deep-dive-card, .comparison-card");

      if (!term) {
        searchableCards.forEach((el) => {
          el.style.display = "";
        });
        return;
      }

      searchableCards.forEach((el) => {
        const text = el.textContent.toLowerCase();
        if (text.includes(term)) {
          el.style.display = "";
        } else {
          el.style.display = "none";
        }
      });
    });

    // คีย์ลัด: Ctrl+K เพื่อโฟกัสช่องค้นหา
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
    });
  }

  // 3. ปุ่มคัดลอกโค้ด (Copy Code Buttons) พร้อมข้อความภาษาไทย
  document.querySelectorAll(".code-block").forEach((block) => {
    const parent = block.parentElement;
    if (!parent) return;

    const copyBtn = document.createElement("button");
    copyBtn.className = "copy-btn";
    copyBtn.innerHTML = `
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
      </svg>
      <span>คัดลอก</span>
    `;

    copyBtn.style.cssText = `
      position: absolute;
      top: 0.6rem;
      right: 0.6rem;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #94a3b8;
      font-size: 0.72rem;
      font-family: inherit;
      padding: 0.25rem 0.6rem;
      border-radius: 4px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.35rem;
      transition: all 0.2s ease;
      z-index: 5;
    `;

    // ครอบ Relative Container
    const container = document.createElement("div");
    container.style.position = "relative";
    block.parentNode.insertBefore(container, block);
    container.appendChild(block);
    container.appendChild(copyBtn);

    copyBtn.addEventListener("click", async () => {
      const codeText = block.textContent;
      try {
        await navigator.clipboard.writeText(codeText);
        copyBtn.innerHTML = `
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2.5">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          <span style="color:#34d399">คัดลอกแล้ว!</span>
        `;
        setTimeout(() => {
          copyBtn.innerHTML = `
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span>คัดลอก</span>
          `;
        }, 2000);
      } catch (err) {
        console.error("Copy failed:", err);
      }
    });
  });

  // 4. ระบบคลิกดูภาพขยายใหญ่เต็มจอ (Image Lightbox Modal)
  const lightbox = document.createElement("div");
  lightbox.id = "imageLightbox";
  lightbox.style.cssText = `
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(5, 7, 10, 0.9);
    backdrop-filter: blur(8px);
    z-index: 9999;
    align-items: center;
    justify-content: center;
    cursor: zoom-out;
  `;

  const lightboxImg = document.createElement("img");
  lightboxImg.style.cssText = `
    max-width: 90vw;
    max-height: 85vh;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.8);
    object-fit: contain;
  `;
  lightbox.appendChild(lightboxImg);
  document.body.appendChild(lightbox);

  document.querySelectorAll(".step-image-preview img, .gallery-img-wrap img, .comparison-img-wrap img").forEach((img) => {
    img.addEventListener("click", () => {
      lightboxImg.src = img.src;
      lightbox.style.display = "flex";
    });
  });

  lightbox.addEventListener("click", () => {
    lightbox.style.display = "none";
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      lightbox.style.display = "none";
    }
  });

  console.log("Project LUMA System Documentation (Thai Edition) initialized.");
})();
