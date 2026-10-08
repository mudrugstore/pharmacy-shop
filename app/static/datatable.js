/*
 datatable เบาๆ ไม่พึ่ง library ภายนอก (เร็วและไฟล์เล็ก)
 ใช้งาน: ใส่ class "js-datatable" ที่ <table> แล้วครอบด้วย element ที่มี toolbar
 คุณสมบัติ: ค้นหาทันที, เรียงคอลัมน์ (คลิกหัวตาราง), แบ่งหน้า
 ตั้งค่าได้ผ่าน data-page-size บน <table> (ค่าเริ่มต้น 10)
*/
(function () {
    function initTable(table) {
        var tbody = table.tBodies[0];
        if (!tbody) return;
        var allRows = Array.prototype.slice.call(tbody.rows);
        var pageSize = parseInt(table.dataset.pageSize, 10) || 10;
        var state = { q: "", sortCol: -1, sortDir: 1, page: 1 };

        // สร้าง toolbar (ช่องค้นหา) เหนือ wrapper
        var wrap = table.closest(".table-wrap") || table.parentNode;
        var toolbar = document.createElement("div");
        toolbar.className = "dt-toolbar";
        toolbar.innerHTML =
            '<input type="search" class="dt-search" placeholder="ค้นหาในตาราง...">' +
            '<span class="dt-count"></span>';
        wrap.parentNode.insertBefore(toolbar, wrap);

        // footer แบ่งหน้า
        var pager = document.createElement("div");
        pager.className = "dt-pager";
        wrap.parentNode.insertBefore(pager, wrap.nextSibling);

        var searchInput = toolbar.querySelector(".dt-search");
        var countEl = toolbar.querySelector(".dt-count");

        // ทำให้หัวตารางคลิกเรียงได้ (ยกเว้นคอลัมน์ที่ไม่มีข้อความ/ปุ่ม)
        var headCells = table.tHead ? table.tHead.rows[0].cells : [];
        Array.prototype.forEach.call(headCells, function (th, idx) {
            if (th.textContent.trim() === "") return;  // คอลัมน์ปุ่ม ไม่ต้องเรียง
            th.classList.add("dt-sortable");
            th.addEventListener("click", function () {
                if (state.sortCol === idx) { state.sortDir *= -1; }
                else { state.sortCol = idx; state.sortDir = 1; }
                Array.prototype.forEach.call(headCells, function (h) { h.removeAttribute("data-sort"); });
                th.setAttribute("data-sort", state.sortDir > 0 ? "asc" : "desc");
                render();
            });
        });

        function cellText(row, i) {
            var c = row.cells[i];
            return c ? c.textContent.trim().toLowerCase() : "";
        }

        function filtered() {
            var q = state.q.toLowerCase();
            var rows = allRows;
            if (q) {
                rows = rows.filter(function (r) {
                    return r.textContent.toLowerCase().indexOf(q) !== -1;
                });
            }
            if (state.sortCol >= 0) {
                rows = rows.slice().sort(function (a, b) {
                    var x = cellText(a, state.sortCol), y = cellText(b, state.sortCol);
                    // เรียงตัวเลขถ้าเป็นตัวเลข (ตัด comma ออก)
                    var nx = parseFloat(x.replace(/[^0-9.-]/g, "")), ny = parseFloat(y.replace(/[^0-9.-]/g, ""));
                    if (!isNaN(nx) && !isNaN(ny) && x.replace(/[0-9.,\s-]/g, "") === "") {
                        return (nx - ny) * state.sortDir;
                    }
                    return x.localeCompare(y, "th") * state.sortDir;
                });
            }
            return rows;
        }

        function render() {
            var rows = filtered();
            var total = rows.length;
            var pages = Math.max(1, Math.ceil(total / pageSize));
            if (state.page > pages) state.page = pages;
            var start = (state.page - 1) * pageSize;
            var pageRows = rows.slice(start, start + pageSize);

            // แสดงเฉพาะแถวของหน้านี้
            allRows.forEach(function (r) { r.style.display = "none"; });
            pageRows.forEach(function (r) { r.style.display = ""; });

            countEl.textContent = total ? ("พบ " + total + " รายการ") : "ไม่พบรายการ";
            renderPager(pages);
        }

        function renderPager(pages) {
            if (pages <= 1) { pager.innerHTML = ""; return; }
            var html = '<button class="dt-pg" data-pg="prev" ' + (state.page === 1 ? "disabled" : "") + '>&laquo;</button>';
            html += '<span class="dt-pginfo">หน้า ' + state.page + " / " + pages + "</span>";
            html += '<button class="dt-pg" data-pg="next" ' + (state.page === pages ? "disabled" : "") + '>&raquo;</button>';
            pager.innerHTML = html;
            pager.querySelectorAll(".dt-pg").forEach(function (b) {
                b.addEventListener("click", function () {
                    if (b.dataset.pg === "prev" && state.page > 1) state.page--;
                    if (b.dataset.pg === "next") state.page++;
                    render();
                });
            });
        }

        // ค้นหาทันทีขณะพิมพ์
        searchInput.addEventListener("input", function () {
            state.q = this.value.trim();
            state.page = 1;
            render();
        });

        render();
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("table.js-datatable").forEach(initTable);
    });
})();
