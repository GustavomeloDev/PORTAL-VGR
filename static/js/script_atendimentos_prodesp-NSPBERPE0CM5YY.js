$(function () {
  // PLUGIN DATATABLES: Ordenação de data no formato dd/mm/yyyy 
  $.fn.dataTable.ext.type.order['date-br-pre'] = function (d) {
    if (!d) return 0;
    var parts = d.split('/');
    if (parts.length < 3) return 0;
    return parseInt(parts[2] + parts[1] + parts[0], 10);
  };

  // 📊 Inicialização do DataTable
  const table = $("#tabela-atendimentos").DataTable({
    ajax: {
      url: "/prodesp/api/atendimentos_list",
      dataSrc: function (json) {
        if (json && json.resumo) updateTopCards(json.resumo);
        return json.atendimentos || [];
      },
      error: function (xhr, error, thrown) {
        console.error("Erro no carregamento da tabela:", thrown);
        showToast("Erro ao carregar dados da tabela. Verifique o console.", "danger");
      }
    },
    processing: true,
    columns: [
      { data: "id_vgr" },
      {
        data: "data_agendamento",
        render: (data) => {
          if (!data) return "";
          // Se a data já contiver o caractere T (ISO datetime), não concatena T00:00:00
          const dateStr = data.includes("T") ? data : data + "T00:00:00";
          const dt = new Date(dateStr);
          return isNaN(dt.getTime()) ? data : dt.toLocaleDateString("pt-BR");
        }
      },
      { data: "hora_agendamento" },
      {
        data: "data_atendimento",
        render: (data, type, row) => {
          if (!data) return "";
          const dt = new Date(data);
          if (isNaN(dt.getTime())) return data;
          if (type === 'sort') return data + (row.horario_inicio || "00:00:00");
          return dt.toLocaleDateString("pt-BR");
        }
      },
      { data: "nome" },
      { data: "status_atendimento" },
      { data: "substatus_atendimento" },
      { data: "analista_atuante" },
      { data: "analista_configuracao" },
      { data: "analista_mpls_atendimentos" },
      { data: "analista_caderno_teste" },
      {
        data: "id_atendimento",
        render: function (data, type, row) {
          let html = '';

          // Ícone do Olho (Visualização)
          if (data) {
            html += `<button class="btn-icon" onclick="viewDetails(${data})" title="Visualizar Atendimento"><i class="fas fa-eye"></i></button>`;
          } else {
            html += `<button class="btn-icon" onclick="viewUnitOnly('${row.id_vgr}')" title="Visualizar Dados da Unidade"><i class="fas fa-eye"></i></button>`;
          }

          // Ícone do Lápis (Edição / Início)
          if (data) {
            const rowDate = row.data_atendimento ? new Date(row.data_atendimento) : null;
            const isToday = rowDate && rowDate.toDateString() === new Date().toDateString();
            if (row.status_atendimento === 'Em Atendimento' && isToday) {
              html += `<button class="btn-icon" onclick="editDetails(${data})" title="Editar Atendimento"><i class="fas fa-pencil-alt"></i></button>`;
            }
          } else {
            // Se não houver atendimento criado, abre o modal de novo atendimento pré-carregado com o ID VGR
            html += `<button class="btn-icon" onclick="openCreateWithVgr('${row.id_vgr}')" title="Iniciar Atendimento"><i class="fas fa-pencil-alt"></i></button>`;
          }
          return html;
        }
      }
    ],
    language: {
      url: "https://cdn.datatables.net/plug-ins/2.3.2/i18n/pt-BR.json",
      search: "🔍",
      paginate: { next: "›", previous: "‹", first: "«", last: "»" },
      columnControl: {
        search: "Pesquisar colunas", orderAsc: "Ordenar asc", orderDesc: "Ordenar desc", orderClear: "Limpar ordenação",
        buttons: { search: "Pesquisar colunas", searchPlaceholder: "Digite para buscar..." },
        list: { all: "Selecionar tudo", empty: "Vazio", none: "Limpar seleção", search: "Buscar..." },
      },
    },
    // ⚙️ Configurações gerais da tabela 
    // ALTERAÇÃO: Ordenação habilitada e configurada para Data + Hora (via data-order)
    ordering: true,
    order: [[3, 'desc']],
    autoWidth: false,
    scrollX: true,
    pageLength: 10,
    lengthMenu: [[5, 10, 25, 50, 100, -1], [5, 10, 25, 50, 100, "Todos"]],
    columnDefs: [
      { targets: 0, width: "6%" }, // ID VGR
      { targets: 1, width: "8%" }, // Data Agendamento
      { targets: 2, width: "8%" }, // Hora Agendamento
      { targets: 3, width: "8%" }, // Data Atendimento
      { targets: 4, width: "15%" }, // Nome Unidade
      { targets: 5, width: "8%" }, // Status
      { targets: 6, width: "10%" }, // Substatus
      { targets: 7, width: "7%" }, // Analista Triagem
      { targets: 8, width: "7%" }, // Analista Remoto
      { targets: 9, width: "7%" }, // Analista MPLS
      { targets: 10, width: "7%" }, // Analista Caderno
      { targets: 11, searchable: false, orderable: false, width: "5%" }, // Ações
      {
        targets: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        columnControl: [
          ["searchList", "spacer", "orderAsc", "orderDesc", "orderClear"],
        ],
      },
    ],
    stateSave: false,

    // 📊 Configurações de busca 
    // 📊 Configurações de exibição
    initComplete: function () {
      const api = this.api();
      const urlParams = new URLSearchParams(window.location.search);
      const idVgrToSearch = urlParams.get("search_id_vgr");
      const openEditId = urlParams.get("open_edit");

      if (idVgrToSearch) {
        const idVgrColumn = api.column(0);
        const idVgrSelect = $(idVgrColumn.header()).find("select");
        idVgrColumn.search("^" + $.fn.dataTable.util.escapeRegex(idVgrToSearch) + "$", true, false).draw();
        if (idVgrSelect.find(`option[value='${idVgrToSearch}']`).length === 0) {
          const newOption = new Option(idVgrToSearch, idVgrToSearch, true, true);
          idVgrSelect.append(newOption);
        }
        idVgrSelect.val([idVgrToSearch]).trigger("change.select2");
      }

      if (openEditId) {
        const newUrlParams = new URLSearchParams(window.location.search);
        newUrlParams.delete("open_edit");
        if (idVgrToSearch) newUrlParams.set("search_id_vgr", idVgrToSearch);
        const newUrl = `${window.location.pathname}?${newUrlParams.toString()}`;
        window.history.replaceState({}, document.title, newUrl);
        setTimeout(() => editDetails(openEditId), 250);
      }
    },
  });

  // Função para atualizar os contadores no topo da página
  function updateTopCards(resumo) {
    if (!resumo) return;
    $("#card-total-geral").text(resumo.total_geral);
    $("#card-total-triagem").text(resumo.substatus_counts["Triagem"] || 0);
    $("#kpi-total").text(resumo.kpis.total);
    $("#kpi-quebra").text(resumo.kpis.quebra);
    $("#kpi-parcial").text(resumo.kpis.parcial);
    $("#kpi-concluido").text(resumo.kpis.concluido);

    // Atualiza cards de substatus dinamicamente
    Object.keys(resumo.substatus_counts).forEach(key => {
      $(`[data-substatus="${key}"] h3`).text(resumo.substatus_counts[key]);
    });
  }

  let motivosForaPadraoCache = [];
  let motivosForaPadraoOriginalEdit = [];

  function getMotivosContainer(context) {
    return document.getElementById(context === "edit" ? "motivos-container-edit" : "motivos-container-create");
  }

  function limparMotivosSelecionados(context) {
    const container = getMotivosContainer(context);
    if (!container) return;
    container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.checked = false;
    });
  }

  function coletarMotivosSelecionados(context) {
    const container = getMotivosContainer(context);
    if (!container) return [];
    return Array.from(container.querySelectorAll('input[type="checkbox"]:checked'))
      .map(cb => parseInt(cb.value, 10))
      .filter(Number.isFinite);
  }

  function arraysIguaisNumeros(a, b) {
    const arrA = [...(a || [])].map(Number).filter(Number.isFinite).sort((x, y) => x - y);
    const arrB = [...(b || [])].map(Number).filter(Number.isFinite).sort((x, y) => x - y);
    if (arrA.length !== arrB.length) return false;
    return arrA.every((val, idx) => val === arrB[idx]);
  }

  window.arraysIguaisNumeros = arraysIguaisNumeros;
  window.renderMotivosView = renderMotivosView;

  function renderMotivosView(container, motivos) {
    if (!container) return;
    container.innerHTML = "";

    if (!motivos || motivos.length === 0) {
      container.innerHTML = '<div class="text-muted small">Nenhum motivo informado.</div>';
      return;
    }

    const motivosPorCategoria = motivos.reduce((acc, item) => {
      const categoria = (item.categoria || "Sem categoria").trim();
      if (!acc[categoria]) acc[categoria] = [];
      acc[categoria].push(item);
      return acc;
    }, {});

    const accordionId = `${container.id}-accordion`;
    const accordion = document.createElement("div");
    accordion.className = "accordion accordion-flush motivos-accordion";
    accordion.id = accordionId;

    Object.keys(motivosPorCategoria).sort().forEach((categoria, index) => {
      const categoryItems = motivosPorCategoria[categoria];
      const item = document.createElement("div");
      item.className = "accordion-item border rounded mb-2 shadow-sm";

      const headerId = `${accordionId}-heading-${index}`;
      const collapseId = `${accordionId}-collapse-${index}`;

      item.innerHTML = `
        <h2 class="accordion-header" id="${headerId}">
          <button class="accordion-button ${index === 0 ? "" : "collapsed"} py-2" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${index === 0 ? "true" : "false"}" aria-controls="${collapseId}">
            <span class="fw-semibold">${categoria}</span>
            <span class="badge text-bg-secondary ms-2">${categoryItems.length}</span>
          </button>
        </h2>
        <div id="${collapseId}" class="accordion-collapse collapse ${index === 0 ? "show" : ""}" aria-labelledby="${headerId}" data-bs-parent="#${accordionId}">
          <div class="accordion-body py-2">
            <div class="d-flex flex-wrap gap-2"></div>
          </div>
        </div>
      `;

      const chips = item.querySelector(".d-flex.flex-wrap");
      categoryItems.forEach(motivo => {
        const badge = document.createElement("span");
        badge.className = "badge text-bg-light border text-dark px-3 py-2 rounded-pill";
        badge.textContent = motivo.descricao || "";
        chips.appendChild(badge);
      });

      accordion.appendChild(item);
    });

    container.appendChild(accordion);
  }

  function renderMotivosForaPadrao(context, motivos, selecionados = []) {
    const container = getMotivosContainer(context);
    if (!container) return;

    container.innerHTML = "";
    const selecionadosSet = new Set((selecionados || []).map(id => parseInt(id, 10)));

    if (!motivos || motivos.length === 0) {
      container.innerHTML = '<div class="col-12"><div class="text-muted small">Nenhum motivo cadastrado.</div></div>';
      return;
    }

    const motivosPorCategoria = motivos.reduce((acc, item) => {
      const categoria = (item.categoria || "Sem categoria").trim();
      if (!acc[categoria]) acc[categoria] = [];
      acc[categoria].push(item);
      return acc;
    }, {});
    const hasAnySelected = (selecionados || []).some(id => Number.isFinite(parseInt(id, 10)));

    const accordionId = `${context}-motivos-accordion`;
    const accordion = document.createElement("div");
    accordion.className = "accordion motivos-accordion";
    accordion.id = accordionId;

    Object.keys(motivosPorCategoria).sort().forEach((categoria, index) => {
      const categoryItems = motivosPorCategoria[categoria];
      const selectedCount = categoryItems.filter(motivo => selecionadosSet.has(parseInt(motivo.id, 10))).length;
      const shouldExpand = selectedCount > 0 || (!hasAnySelected && index === 0);
      const item = document.createElement("div");
      item.className = "accordion-item border rounded mb-2 shadow-sm";
      if (selectedCount > 0) item.classList.add("motivos-selected");

      const headerId = `${accordionId}-heading-${index}`;
      const collapseId = `${accordionId}-collapse-${index}`;

      item.innerHTML = `
        <h2 class="accordion-header" id="${headerId}">
          <button class="accordion-button ${index === 0 ? "" : "collapsed"} py-2" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${index === 0 ? "true" : "false"}" aria-controls="${collapseId}">
            <span class="fw-semibold">${categoria}</span>
            <span class="badge text-bg-${selectedCount > 0 ? "success" : "secondary"} ms-2 motivos-selection-badge">${selectedCount}/${categoryItems.length}</span>
          </button>
        </h2>
        <div id="${collapseId}" class="accordion-collapse collapse ${shouldExpand ? "show" : ""}" aria-labelledby="${headerId}" data-bs-parent="#${accordionId}">
          <div class="accordion-body py-2">
            <div class="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-2"></div>
          </div>
        </div>
      `;

      const grid = item.querySelector(".row");
      categoryItems.forEach(motivo => {
        const col = document.createElement("div");
        col.className = "col";

        const wrapper = document.createElement("label");
        wrapper.className = "form-check border rounded p-2 h-100 d-flex align-items-start gap-2 bg-white motivos-option";
        wrapper.setAttribute("for", `${context}-motivo-${motivo.id}`);

        const input = document.createElement("input");
        input.className = "form-check-input mt-1";
        input.type = "checkbox";
        input.id = `${context}-motivo-${motivo.id}`;
        input.value = motivo.id;
        input.checked = selecionadosSet.has(parseInt(motivo.id, 10));

        const text = document.createElement("span");
        text.className = "fw-medium small";
        text.textContent = motivo.descricao || "";

        wrapper.prepend(input);
        wrapper.appendChild(text);
        col.appendChild(wrapper);
        grid.appendChild(col);
      });

      accordion.appendChild(item);
    });

    container.appendChild(accordion);

    container.onchange = () => {
      container.querySelectorAll(".accordion-item").forEach(section => {
        const total = section.querySelectorAll('input[type="checkbox"]').length;
        const selected = section.querySelectorAll('input[type="checkbox"]:checked').length;
        const badge = section.querySelector(".motivos-selection-badge");
        if (badge) {
          badge.textContent = `${selected}/${total}`;
          badge.classList.remove("text-bg-secondary", "text-bg-success");
          badge.classList.add(selected > 0 ? "text-bg-success" : "text-bg-secondary");
        }
        section.classList.toggle("motivos-selected", selected > 0);
      });
    };
  }

  async function carregarMotivosForaPadrao(context) {
    if (!motivosForaPadraoCache.length) {
      const response = await fetch("/prodesp/api/motivos_fora_padrao");
      if (!response.ok) {
        throw new Error("Não foi possível carregar os motivos fora do padrão.");
      }
      motivosForaPadraoCache = await response.json();
    }
    renderMotivosForaPadrao(context, motivosForaPadraoCache, []);
  }

  async function marcarMotivosAtendimento(context, idAtendimento) {
    const response = await fetch(`/prodesp/api/atendimento/${idAtendimento}/motivos`);
    if (!response.ok) {
      throw new Error("Não foi possível carregar os motivos do atendimento.");
    }
    const selecionados = await response.json();
    renderMotivosForaPadrao(context, motivosForaPadraoCache, selecionados);
    return selecionados;
  }

  window.limparMotivosSelecionados = limparMotivosSelecionados;
  window.coletarMotivosSelecionados = coletarMotivosSelecionados;
  window.carregarMotivosForaPadrao = carregarMotivosForaPadrao;
  window.marcarMotivosAtendimento = marcarMotivosAtendimento;
  window.renderMotivosForaPadrao = renderMotivosForaPadrao;

  // Temporizador de Atualização (3 minutos)
  const REFRESH_INTERVAL = 3 * 60 * 1000;
  setInterval(() => {
    const isModalOpen = $(".modal.show").length > 0;
    if (!isModalOpen) {
      table.ajax.reload(null, false); // false para manter a paginação atual
    }
  }, REFRESH_INTERVAL);

  // --- FILTRO POR CARDS ---
  $('.filter-card').on('click', function () {
    const substatus = $(this).data('substatus');
    const columnIndex = 6; // Coluna de Substatus

    // Limpa a pesquisa existente (global e colunas)
    table.search('').columns().search('');

    // Limpa visualmente os selects do ColumnControl em todas as colunas
    table.columns().every(function () {
      if (this.columnControl && this.columnControl.searchList()) {
        this.columnControl.searchList().val(null).trigger('change.select2');
      }
    });

    if (substatus === 'all') {
      table.draw();
    } else {
      const column = table.column(columnIndex);
      if (column.columnControl && column.columnControl.searchList()) {
        // Aplica o filtro via ColumnControl (atualiza visual e dispara busca)
        column.columnControl.searchList().val([substatus]).trigger('change');
      } else {
        // Fallback: Busca exata pelo substatus na coluna 5
        column.search('^' + $.fn.dataTable.util.escapeRegex(substatus) + '$', true, false).draw();
      }
    }

    // Adiciona a animação de scroll
    $('html, body').animate({
      scrollTop: $('#tabela-atendimentos').offset().top
    }, 500);
  });
  $(window).on("resize", () => table.columns.adjust());

  // --- MÁSCARAS ---
  const coordinateMaskDefinition = { mask: Number, signed: true, scale: 8, radix: '.', mapToRadix: [','], normalizeZeros: true, padFractionalZeros: false };
  ['editLatitude', 'editLongitude', 'createLatitude', 'createLongitude'].forEach(id => {
    const el = document.getElementById(id);
    if (el) maskInstances[id] = IMask(el, coordinateMaskDefinition);
  });

  const serialMaskDefinition = { mask: /^[a-zA-Z0-9\-]*$/, prepare: str => str.toUpperCase() };

  [
    { id: 'editEquipamentoSerial', mask: serialMaskDefinition }, { id: 'createEquipamentoSerial', mask: serialMaskDefinition }
  ].forEach(field => {
    const el = document.getElementById(field.id);
    if (el) maskInstances[field.id] = IMask(el, field.mask);
  });

  // --- MÁSCARAS E VALIDAÇÃO PARA IP / MÁSCARA REDE ---
  const ipMaskDefinition = { mask: /^[0-9\.]*$/ };
  const ipFields = [
    'editIpLan01', 'createIpLan01', 'editIpLan02', 'createIpLan02',
    'editIpLanTransito', 'createIpLanTransito',
    'editLoopbackVivo', 'createLoopbackVivo',
    'editLoopbackCliente', 'createLoopbackCliente',
    'editLinkIpWan', 'createLinkIpWan',
    'editLinkIpGateway', 'createLinkIpGateway',
    'editLinkIpMascara', 'createLinkIpMascara'
  ];

  ipFields.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      maskInstances[id] = IMask(el, ipMaskDefinition);
      
      el.addEventListener('blur', () => {
        const val = el.value.trim();
        if (val === '') {
          el.classList.remove('is-invalid');
          return;
        }
        
        // Regex para validar IPv4 (cada octeto entre 0 e 255)
        const ipv4Regex = /^(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
        
        if (val.length < 7 || !ipv4Regex.test(val)) {
          el.classList.add('is-invalid');
          const label = document.querySelector(`label[for="${id}"]`)?.textContent || 'IP';
          showToast(`O campo "${label}" deve conter um endereço IPv4 válido (ex: 192.168.0.1).`, 'warning');
        } else {
          el.classList.remove('is-invalid');
        }
      });
    }
  });

  // --- LÓGICA PARA LINKS CONDICIONAIS ---
  function handleLinkTypeChange(context) {
    const typeSelect = document.getElementById(`${context}LinkTipo`);
    if (!typeSelect) return;

    const selectedType = typeSelect.value;
    const container = document.getElementById(`${context}-link-fields-container`);
    if (!container) return;

    const fields = container.querySelectorAll('.link-field-wrapper');

    fields.forEach(field => {
      const linkTypeAttr = field.dataset.linkType;
      let supportedTypes = linkTypeAttr ? linkTypeAttr.split(' ') : [];

      if (supportedTypes.includes(selectedType)) {
        field.style.display = '';
      } else {
        field.style.display = 'none';
        const input = field.querySelector('input');
        if (input) input.value = '';
      }
    });
  }

  ['create', 'edit'].forEach(context => {
    const typeSelect = document.getElementById(`${context}LinkTipo`);
    if (typeSelect) {
      typeSelect.addEventListener('change', () => handleLinkTypeChange(context));
      handleLinkTypeChange(context); // Initial call
    }
  });

  // --- LÓGICA PARA DESCRIÇÃO AUTOMÁTICA DE EQUIPAMENTOS ---
  ['create', 'edit'].forEach(context => {
    const modeloSelect = document.getElementById(`${context}EquipamentoModelo`);
    const descricaoInput = document.getElementById(`${context}EquipamentoDescricao`);
    
    if (modeloSelect && descricaoInput) {
      modeloSelect.addEventListener('change', function() {
        const selectedModel = this.value; // Get the selected model value
        const autoDescModels = [
          "FortiGate 40F", "FortiGate 60F", "FortiGate 120G", 
          "FortiGate 900G", "FortiGate 3200F", "FortiGate 3700F",
          "FortiGate 600F" // Include FortiGate 600F in auto-description
        ];
        
        // Clear previous description
        descricaoInput.value = "";
        
        if (autoDescModels.includes(selectedModel)) {
          descricaoInput.value = "Firewall - Stand Alone";
        } else if (selectedModel === "FortiSwitch 2048F") {
          descricaoInput.value = "Switch"; // Specific description for FortiSwitch
        }
      });
    }
  });

  // --- COLLAPSE ICON TOGGLE ---
  $('.chart-collapse').on('show.bs.collapse', function () {
    $(this).parent().find('.card-header button i').removeClass('fa-plus').addClass('fa-minus');
  }).on('hide.bs.collapse', function () {
    $(this).parent().find('.card-header button i').removeClass('fa-minus').addClass('fa-plus');
  });
});

// Objeto para armazenar as instâncias das máscaras (escopo global)
const maskInstances = {};

// ----------------------------------------------------------------------------------------
//FUNÇÕES PARA MÁSCARA DE TELEFONE
// ----------------------------------------------------------------------------------------
function aplicarMascaraTelefone(input) {
  input.addEventListener("input", () => {
    let valor = input.value.replace(/\D/g, ""); // Remove tudo que não é número
    let maskedValue = "";
    const isCelularComNove = valor.length >= 3 && valor.charAt(2) === "9"; // Determina o tipo de número pelo terceiro dígito (o primeiro após o DDD) // Assume que se tiver menos de 3 dígitos, ainda não sabemos o tipo.
    const maxDigits = isCelularComNove ? 11 : 10; // 11 para celular (DD + 9xxxx-xxxx), 10 para fixo (DD + xxxx-xxxx) // Define o limite máximo de dígitos para o número limpo
    if (valor.length > maxDigits) {
      valor = valor.slice(0, maxDigits);
    }

    // Aplica a máscara
    if (valor.length > 0) {
      maskedValue = `(${valor.slice(0, 2)}`; // (XX
    }
    if (valor.length > 2) {
      if (isCelularComNove) {
        // Formato para celular 9xxxx-xxxx (11 dígitos no total)
        if (valor.length <= 7) {
          // Até o 5º dígito do número (ex: 95475)
          maskedValue += `) ${valor.slice(2)}`;
        } else {
          // Depois do 5º dígito do número (ex: 95475-8008)
          maskedValue += `) ${valor.slice(2, 7)}-${valor.slice(7)}`;
        }
      } else {

        if (valor.length <= 6) {
          // Até o 4º dígito do número (ex: 4051)
          maskedValue += `) ${valor.slice(2)}`;
        } else {
          // Depois do 4º dígito do número (ex: 4051-3220)
          maskedValue += `) ${valor.slice(2, 6)}-${valor.slice(6)}`;
        }
      }
    }

    input.value = maskedValue;
  });

  // Impede colar caracteres inválidos e aplica a máscara
  input.addEventListener("paste", (e) => {
    const paste = (e.clipboardData || window.clipboardData).getData("text");
    const cleanedPaste = paste.replace(/\D/g, ""); // Remove não-dígitos da string colada

    // Apenas se o que foi colado (limpo) for inteiramente dígitos
    if (!/^\d+$/.test(cleanedPaste)) {
      e.preventDefault(); // Impede a colagem se contiver algo além de números
    } else {
      // Permite a colagem, mas depois dispara o evento 'input' para aplicar a máscara e o limite
      e.preventDefault(); // Previne a colagem padrão para controlar o que entra
      input.value = cleanedPaste; // Define o valor limpo
      setTimeout(() => {
        input.dispatchEvent(new Event("input")); // Dispara o evento 'input' para aplicar a máscara e o limite
      }, 0);
    }
  });

  // Impede digitação de letras ou símbolos
  input.addEventListener("keypress", (e) => {
    // Permite apenas dígitos
    if (!/\d/.test(e.key)) {
      e.preventDefault();
    }
  });
}

$(function () {
  const phoneFields = ['editContatoField', 'editTelefoneContato', 'createContatoField', 'createTelefoneContato'];
  phoneFields.forEach(id => {
    const element = document.getElementById(id);
    if (element) {
      aplicarMascaraTelefone(element);
    }
  });
});

/**
 * Copia o texto de um campo ao clicar no ícone.
 * @param {Event} event O evento de clique.
 */
function handleCopyClick(event) {
  const copyBtn = event.target.closest('.btn-copy, .btn-copy-inline');
  if (!copyBtn) return; // Sai se o clique não foi em um botão/ícone de cópia

  let textToCopy = '';

  // Lógica para botões dentro de um input-group
  if (copyBtn.classList.contains('btn-copy')) {
    const input = copyBtn.closest('.input-group').querySelector('input, select');
    if (input) {
      textToCopy = input.value;
    }
  }
  // Lógica para ícones dentro da lista de equipamentos
  else if (copyBtn.classList.contains('btn-copy-inline')) {
    // Pega o texto do nó pai, removendo o texto do próprio ícone
    const parent = copyBtn.parentNode;
    const clone = parent.cloneNode(true);
    clone.removeChild(clone.querySelector('.btn-copy-inline'));
    textToCopy = clone.textContent.trim();
  }

  if (textToCopy) {
    navigator.clipboard.writeText(textToCopy).then(() => {
      showToast(`'${textToCopy}' copiado!`, 'success');
    }).catch(err => {
      console.error('Erro ao copiar:', err);
      showToast('Falha ao copiar para a área de transferência.', 'danger');
    });
  } else {
    showToast('Nada para copiar.', 'info');
  }
}

// Adiciona os listeners de clique aos modais usando delegação de eventos
document.addEventListener('DOMContentLoaded', () => {
  const editModalEl = document.getElementById('editModal');
  const createModalEl = document.getElementById('createModal');
  if (editModalEl) editModalEl.addEventListener('click', handleCopyClick);
  if (createModalEl) createModalEl.addEventListener('click', handleCopyClick);
});

/**
 * Exibe uma notificação (toast).
 * @param {string} message Mensagem a ser exibida.
 * @param {string} type Tipo do toast: 'success', 'danger', 'warning', 'info'.
 */
function showToast(message, type = "info", delay = 15000) {
  const toastContainer = document.querySelector(".toast-container");
  if (!toastContainer) {
    console.error("Toast container not found!");
    alert(message);
    return;
  }

  const toastId = "toast-" + Date.now();
  const toastHeaderClass =
    {
      success: "bg-success text-white",
      danger: "bg-danger text-white",
      warning: "bg-warning text-dark",
      info: "bg-primary text-white",
    }[type] || "bg-secondary text-white";

  const toastIcon =
    {
      success: '<i class="fas fa-check-circle me-2"></i>',
      danger: '<i class="fas fa-times-circle me-2"></i>',
      warning: '<i class="fas fa-exclamation-triangle me-2"></i>',
      info: '<i class="fas fa-info-circle me-2"></i>',
    }[type] || '<i class="fas fa-bell me-2"></i>';

  const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${toastHeaderClass}">
                ${toastIcon}
                <strong class="me-auto">Atenção</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">${message}</div>
        </div>`;

  toastContainer.insertAdjacentHTML("beforeend", toastHtml);
  const toastElement = document.getElementById(toastId);
  const toast = new bootstrap.Toast(toastElement, { delay: delay });
  toastElement.addEventListener("hidden.bs.toast", () => toastElement.remove());
  toast.show();
}

/**
 * Controla o estado de carregamento de um botão.
 * @param {HTMLButtonElement} button O botão.
 * @param {boolean} isLoading True para mostrar o spinner, false para reverter.
 * @param {string} [loadingText='Aguarde...'] Texto durante o carregamento.
 */
function setButtonLoading(button, isLoading, loadingText = 'Aguarde...') {
  if (!button) return;

  if (isLoading) {
    // Salva o texto original do botão.
    if (!button.dataset.originalContent) {
      button.dataset.originalContent = button.innerHTML;
    }
    const spinner = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
    button.innerHTML = `${spinner} ${loadingText}`;
    button.disabled = true;
  } else {
    // Restaura o texto original e reabilita o botão.
    if (button.dataset.originalContent) {
      button.innerHTML = button.dataset.originalContent;
    }
    button.disabled = false;
  }
}

// ------------------------------------------------------------------------------------------------
// FUNÇÕES PARA O CAMPO SUBSTATUS
// ------------------------------------------------------------------------------------------------
/**
 * Preenche o select de substatus conforme o status.
 * @param {HTMLSelectElement} substatusSelectEl O elemento <select> do substatus.
 * @param {string} statusValue O valor do status selecionado.
 * @param {string} currentSubstatus O valor atual do substatus.
 * @param {string} userDepartment O departamento do usuário (global ou passado).
 * @param {object} gruposFilas Objeto com a configuração de grupos e substatus.
 */
function populateSubstatus(substatusSelectEl, statusValue, currentSubstatus = null, userDepartment = (typeof USER_DEPARTMENT !== 'undefined' ? USER_DEPARTMENT : 'TODOS'), gruposFilas = (typeof GRUPOS_FILAS_JS !== 'undefined' ? GRUPOS_FILAS_JS : {}), context) {
  if (!substatusSelectEl) return;

  const currentValue = substatusSelectEl.value ? substatusSelectEl.value.trim() : "";
  const statusValueClean = statusValue ? statusValue.trim() : "";
  const substatusToRestore = (currentSubstatus !== null ? currentSubstatus.toString().trim() : currentValue);

  substatusSelectEl.innerHTML = '<option selected disabled value="">Selecione o Substatus...</option>';
  substatusSelectEl.disabled = !statusValueClean;

  if (!statusValueClean) return;

  let options = [];
  if (statusValueClean === "Em Atendimento") {
    // Define the ordered progression of substatuses
    const orderedProgression = [
      "Triagem",
      "Aguardando Config. Remota",
      "Em Configuração Remota",
      "Aguardando Config. MPLS",
      "Em Configuração do MPLS", // Ensure this matches backend exactly
      "Aguardando Caderno de Teste",
      "Em Caderno de Teste"
    ];

    let allowedSubstatusesForSelection = [];
    const previousAllowed = ["Triagem", "Aguardando Config. Remota", "Aguardando Config. MPLS", "Aguardando Caderno de Teste"];

    if (!substatusToRestore || substatusToRestore === "") {
      // Rule: Ao iniciar, permite Triagem e libera o próximo passo da fila (Aguardando Config. Remota)
      allowedSubstatusesForSelection = ["Triagem", "Aguardando Config. Remota"];
    } else {
      const currentIndex = orderedProgression.indexOf(substatusToRestore);

      if (currentIndex === -1) {
        // Current substatus is not in the defined progression, allow all "Em Atendimento" substatuses as a fallback
        allowedSubstatusesForSelection = orderedProgression;
      } else if (currentSubstatus === "Aguardando Caderno de Teste") {
        // Rule: "Aguardando Caderno de Teste" todas as opções disponiveis.
        allowedSubstatusesForSelection = orderedProgression;
      } else {
        // Regra: Substatus seguintes continuam normais (atual + 1). 
        // Regra: Substatus anteriores devem ser apenas os permitidos (Triagem e Aguardando...)
        for (let i = 0; i < orderedProgression.length; i++) {
          const sub = orderedProgression[i];
          if (i < currentIndex) {
            if (previousAllowed.includes(sub)) allowedSubstatusesForSelection.push(sub);
          } else if (i <= currentIndex + 1) {
            allowedSubstatusesForSelection.push(sub);
          }
        }
      }
    }

    // Preenche as opções respeitando a ordem visual solicitada de cima para baixo
    orderedProgression.forEach(sub => {
      if (allowedSubstatusesForSelection.includes(sub)) {
        options.push({ value: sub, text: sub });
      }
    });
  } else if (statusValueClean === "Concluído") {
    options.push({ value: "Concluído", text: "Concluído" });
  } else if (statusValueClean === "Concluído Parcial") {
    options.push({ value: "Pendente Configuração Remota", text: "Pendente Configuração Remota" }, { value: "Pendente Configuração MPLS", text: "Pendente Configuração MPLS" }, { value: "Quebra Field", text: "Quebra Field" }, { value: "Pendente Link IPD", text: "Pendente Link IPD" }, { value: "Pendente Link MPLS", text: "Pendente Link MPLS" });
  } else if (statusValueClean === "Quebra") {
    options.push({ value: "Quebra Link", text: "Quebra Link" }, { value: "Quebra Infra", text: "Quebra Infra" }, { value: "Quebra Hardware", text: "Quebra Hardware" }, { value: "Quebra Field", text: "Quebra Field" }, { value: "Quebra Cliente", text: "Quebra Cliente" });
  }

  options.forEach(opt => substatusSelectEl.add(new Option(opt.text, opt.value)));

  // Tenta restaurar o valor anterior. Se estiver vazio (novo atendimento), tenta selecionar "Triagem" por padrão
  let valueToSet = options.some(opt => opt.value === substatusToRestore) ? substatusToRestore : "";
  
  if (valueToSet === "" && options.some(opt => opt.value === "Triagem")) {
    valueToSet = "Triagem";
  } else if (valueToSet === "" && options.length === 1) {
    valueToSet = options[0].value;
  }

  substatusSelectEl.value = valueToSet;

  // // Auto-select "Concluído" if status is "Concluído"
  // if (statusValue === "Concluído") {
  //   substatusSelectEl.value = "Concluído";
  // }

  // Lógica para preencher automaticamente o campo de analista com base no substatus
  if (statusValueClean === "Em Atendimento" && typeof USUARIO_LOGADO !== 'undefined' && USUARIO_LOGADO && context) {
    const analystFieldsMap = {
      "Triagem": document.getElementById(`${context}AnalistaAtuante`),
      "Em Configuração Remota": document.getElementById(`${context}AnalistaConfiguracao`),
      "Em Configuração do MPLS": document.getElementById(`${context}AnalistaMplsAtendimentos`),
      "Em Caderno de Teste": document.getElementById(`${context}AnalistaCadernoTeste`)
    };

    const selectedSubstatus = substatusSelectEl.value;
    const targetAnalystField = analystFieldsMap[selectedSubstatus];

    if (targetAnalystField) {
      // Preenche apenas se o campo estiver vazio. 
      // Não substitui se já houver um analista populado.
      if (!targetAnalystField.value || targetAnalystField.value.trim() === '') {
        targetAnalystField.value = USUARIO_LOGADO;
        targetAnalystField.dispatchEvent(new Event('input', { bubbles: true })); // Dispara evento para auto-save
      }
    }
  }
}

// ------------------------------------------------------------------------------------------------
// FUNÇÃO PARA UPDATE DO MODAL DE EDIÇÃO
// ------------------------------------------------------------------------------------------------
let originalData = {};

/**
 * Desabilita/habilita todos os campos do formulário de edição.
 * @param {boolean} isDisabled True para desabilitar, false para habilitar.
 */
function setAllEditFieldsDisabled(isDisabled) {
  const form = document.getElementById("editForm");
  const elements = form.querySelectorAll("input, select, textarea");
  elements.forEach((el) => {
    if (el.type !== "hidden") {
      // Usa 'readOnly' em campos de texto para permitir cópia do conteúdo.
      if (
        el.tagName === "TEXTAREA" ||
        (el.tagName === "INPUT" &&
          ["text", "tel", "email", "number", "url"].includes(el.type))
      ) {
        // Mantém os campos de analista e descrição de equipamentos sempre bloqueados para edição manual
        const isAnalystField = el.id.toLowerCase().includes("analista");
        const isDescriptionField = el.id.toLowerCase().includes("equipamentodescricao");
        el.readOnly = (isAnalystField || isDescriptionField) ? true : isDisabled;
      } else {
        // Para 'select', 'checkbox', 'radio' e outros tipos de 'input', usa 'disabled'.
        el.disabled = isDisabled;
      }
    }
  });

  // Desabilita/habilita os botões de "Adicionar"
  document.getElementById("btn-add-observacao-edit").disabled = isDisabled;
  document.getElementById("btn-add-equipamento-edit").disabled = isDisabled;
  document.getElementById("btn-add-link-edit").disabled = isDisabled;
  // O botão Salvar é controlado separadamente
}


// ------------------------------------------------------------------------------------------------------
// FUNÇÃO PARA AUTO-SALVAR DADOS NO MODAL DE EDIÇÃO
// ------------------------------------------------------------------------------------------------------
let autoSaveEditTimeout = null;
let existingEquipments = []; // Array para armazenar equipamentos existentes e facilitar a validação
let existingLinks = []; // Array para armazenar links existentes e facilitar a validação
let existingLinksCreate = []; // Array para links no modal de criação
let editingEquipmentId = null; // ID do equipamento em edição
let editingLinkId = null;      // ID do link em edição

async function autoSaveEditModalData() {
  const id = +document.getElementById("editAtendimentoId").value;
  if (!id) {
    console.warn("Attempted auto-save for edit modal without an existing attendance ID.");
    return;
  }

  const updates = [];
  const motivosForaPadrao = coletarMotivosSelecionados("edit");

  const editableJsFields = [
    "logs",
    "status",
    "substatus",
    "analista_atuante",
    "analista_configuracao",
    "analista_mpls_atendimentos",
    "analista_caderno_teste",
    "contratada",
    "field",
    "contato_field",

    "nome",
    "acronimo",
    "hostname",
    "endereco",
    "numero",
    "bairro",
    "municipio",
    "estado",
    "complemento",
    "data_agendamento",
    "hora_agendamento",
    "cep",
    "latitude",
    "longitude",
    "telefone_contato",
    "ip_lan_01",
    "ip_lan_02",
    "ip_lan_transito",
    "id_intragov",
    "loopback_vivo",
    "loopback_cliente",
  ];

  const keyMap = {
    status: "status_atendimento",
    substatus: "substatus_atendimento",
    analista_atuante: "analista_atuante",
    analista_configuracao: "analista_configuracao",
    analista_mpls_atendimentos: "analista_mpls_atendimentos",
    analista_caderno_teste: "analista_caderno_teste_atendimentos",
    contratada: "contratada",
    field: "field_responsavel",
    contato_field: "contato_field",
    logs: "logs_atendimentos",
    nome: "nome",
    acronimo: "acronimo_unidades",
    hostname: "hostname_unidades",
    endereco: "endereco_unidades",
    numero: "numero_unidades",
    bairro: "bairro_unidades",
    municipio: "municipio_unidades",
    estado: "estado_unidades",
    complemento: "complemento_unidades",
    data_agendamento: "data_agendamento_unidades",
    hora_agendamento: "hora_agendamento_unidades",
    cep: "cep_unidades",
    latitude: "latitude_unidades",
    longitude: "longitude_unidades",
    telefone_contato: "telefone_contato_unidades",
    ip_lan_01: "ip_lan_01_unidades",
    ip_lan_02: "ip_lan_02_unidades",
    id_intragov: "id_intragov_unidades",
    loopback_vivo: "loopback_vivo_unidades",
    loopback_cliente: "loopback_cliente_unidades",
  };

  editableJsFields.forEach((col) => {
    let novo;
    if (col === "logs") {
      novo = logsEdit.map(l => `[${l.timestamp}] ${l.user}: ${l.text}`).join('\n');
    } else {
      const el = document.getElementById(idFor("edit", col));
      if (!el) return;
      novo = maskInstances[el.id] ? maskInstances[el.id].unmaskedValue : el.value;
    }

    // Previne envio de string vazia para campos de data, hora ou coordenadas (evita erro no MySQL)
    if (novo === "" && ["data_agendamento", "hora_agendamento", "latitude", "longitude"].includes(col)) {
      novo = null;
    }

    const originalKey = keyMap[col];
    if (!originalKey) return;

    const antigo = (originalData[originalKey] || "").toString();

    if (novo !== antigo) {
      updates.push({
        coluna: col,
        valor: novo,
      });
    }
  });

  let allSuccess = true;

  // 1. Atualizar os principais campos
  if (updates.length > 0 || !arraysIguaisNumeros(motivosForaPadrao, motivosForaPadraoOriginalEdit)) {
    try {
      const resMain = await fetch("/prodesp/atendimentos/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: id,
          updates: updates,
          motivos_fora_padrao: motivosForaPadrao,
          finalizing: false
        }),
      });
      const resultMain = await resMain.json();
      if (!resultMain.success) {
        console.error("Auto-save (Edit): Erro ao atualizar dados principais: " + resultMain.message);

        // Exibe o aviso de concorrência ou erro retornado pelo backend
        showToast(resultMain.message, 'danger');
        allSuccess = false;

        // Se houver conflito (409), recarrega a página para atualizar o estado real do atendimento
        if (resMain.status === 409) {
          setTimeout(() => location.reload(), 3500);
        }
      } else {
        updates.forEach((u) => {
          const originalKey = Object.keys(keyMap).find(
            (key) => keyMap[key] === u.coluna
          );
          if (originalKey) {
            originalData[keyMap[originalKey]] = u.valor;
          }
        });
        motivosForaPadraoOriginalEdit = [...motivosForaPadrao];
      }
    } catch (err) {
      console.error("Auto-save (Edit): Falha ao atualizar dados principais.", err);
      allSuccess = false;
    }
  }

  // 2. salve nova observações
  if (newObservacao.length > 0 || deletedObservacaoIds.length > 0) {
    const observationsToSave = [...newObservacao];
    newObservacao.length = 0;

    try {
      const respObs = await fetch("/prodesp/observacoes-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          new_observacoes: observationsToSave,
          deleted_observacoes: deletedObservacaoIds,
        }),
      });
      const resultObs = await respObs.json();
      if (!resultObs.success) {
        console.error("Auto-save (Edit): Erro ao salvar observações: " + resultObs.message);
        newObservacao.push(...observationsToSave);
        allSuccess = false;
      } else {
        deletedObservacaoIds.length = 0;
      }
    } catch (err) {
      console.error("Auto-save (Edit): Falha ao salvar observações.", err);
      newObservacao.push(...observationsToSave);
      allSuccess = false;
    }
  }

  // 3. Salve novo equipamentos e deleta
  if (newEquipamentoEdit.length > 0 || deletedEquipamentoIds.length > 0) {
    const equipmentsToSave = [...newEquipamentoEdit];
    newEquipamentoEdit.length = 0;

    try {
      const respEq = await fetch("/prodesp/equipamentos-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          id_unidade_equipamentos: originalData.id_unidades_atendimentos,
          new_equipamentos: equipmentsToSave,
          deleted_equipamentos: deletedEquipamentoIds,
        }),
      });
      const resultEq = await respEq.json();
      if (!resultEq.success) {
        console.error("Auto-save (Edit): Erro ao salvar equipamentos: " + resultEq.message);
        newEquipamentoEdit.push(...equipmentsToSave);
        allSuccess = false;
      } else {
        deletedEquipamentoIds.length = 0;
      }
    } catch (err) {
      console.error("Auto-save (Edit): Falha ao salvar equipamentos.", err);
      newEquipamentoEdit.push(...equipmentsToSave);
      allSuccess = false;
    }
  }

  // 4. Salve novos links e deleta
  if (newLinksEdit.length > 0 || deletedLinkIds.length > 0) {
    const linksToSave = [...newLinksEdit];
    newLinksEdit.length = 0;

    try {
      const respLnk = await fetch("/prodesp/links-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          id_unidade_links: originalData.id_unidades_atendimentos,
          id_vgr: document.getElementById("editIdVgr").value.trim(),
          new_links: linksToSave,
          deleted_links: deletedLinkIds,
        }),
      });
      const resultLnk = await respLnk.json();
      if (!resultLnk.success) {
        console.error("Auto-save (Edit): Erro ao salvar links: " + resultLnk.message);
        newLinksEdit.push(...linksToSave);
        allSuccess = false;
      } else {
        deletedLinkIds.length = 0;
      }
    } catch (err) {
      console.error("Auto-save (Edit): Falha ao salvar links.", err);
      newLinksEdit.push(...linksToSave);
      allSuccess = false;
    }
  }

  if (allSuccess) {
    console.log("Auto-save (Edit) completo para atendimento ID:", id);
  } else {
    console.error("Auto-save (Edit) falhou para atendimento ID:", id);
  }
}

/**
 * Preenche os campos de um modal (Edição ou Visualização) com os dados do atendimento.
 * @param {Object} d - Objeto com os dados do atendimento.
 * @param {string} prefix - Prefixo dos IDs dos elementos ('edit' ou 'view').
 */
function fillModalFields(d, prefix) {
  const setVal = (id, val) => {
    const el = document.getElementById(prefix + id);
    if (el) el.value = (val && typeof val === 'string') ? val.trim() : (val || "");
  };

  if (prefix === 'edit') {
    setVal("AtendimentoId", d.id_atendimentos);
  }

  setVal("Status", d.status_atendimento);

  // Popula substatus apenas para edição, para visualização é apenas input text
  if (prefix === 'edit') {
    const substatusSelect = document.getElementById("editSubstatus"); // Passa o contexto 'edit'
    // Garante que os valores iniciais estão limpos de espaços para evitar falha no select
    const statusInit = d.status_atendimento ? d.status_atendimento.trim() : "";
    const substatusInit = d.substatus_atendimento ? d.substatus_atendimento.trim() : "";
    populateSubstatus(substatusSelect, statusInit, substatusInit, undefined, undefined, 'edit');
  } else {
    setVal("Substatus", d.substatus_atendimento);
  }

  setVal("AnalistaAtuante", d.analista_atuante);
  setVal("AnalistaConfiguracao", d.analista_configuracao);
  setVal("AnalistaMplsAtendimentos", d.analista_mpls_atendimentos);
  setVal("AnalistaCadernoTeste", d.analista_caderno_teste);
  setVal("Contratada", d.contratada);
  setVal("Field", d.field_responsavel);
  setVal("ContatoField", d.contato_field);

  if (prefix === 'view') {
    setVal("Logs", d.logs_atendimento);
    const motivosContainer = document.getElementById("viewMotivosForaPadrao");
    window.renderMotivosView(motivosContainer, d.motivos_fora_padrao || []);
  } else {
    reloadLogs(d.logs_atendimento, document.getElementById(`log-configuracao-remota-${prefix}`), prefix);
  }

  setVal("IdVgr", d.id_vgr);
  setVal("Nome", d.nome);
  setVal("Acronimo", d.acronimo);
  setVal("Hostname", d.hostname);
  setVal("TelefoneContato", d.telefone_contato);
  setVal("Endereco", d.endereco);
  setVal("Numero", d.numero);
  setVal("Complemento", d.complemento);
  setVal("Bairro", d.bairro);
  setVal("Municipio", d.municipio);
  setVal("Estado", d.estado);
  setVal("Cep", d.cep);
  setVal("DataAgendamento", d.data_agendamento);
  setVal("HoraAgendamento", d.hora_agendamento);

  // Máscaras
  if (prefix === 'edit') {
    if (maskInstances.editLatitude) maskInstances.editLatitude.value = String(d.latitude || '');
    if (maskInstances.editLongitude) maskInstances.editLongitude.value = String(d.longitude || '');
  } else {
    setVal("Latitude", d.latitude);
    setVal("Longitude", d.longitude);
  }

  setVal("IpLan01", d.ip_lan_01);
  setVal("IpLan02", d.ip_lan_02);
  setVal("IpLanTransito", d.ip_lan_transito);
  setVal("Idintragov", d.id_intragov); // Corrigido mapeamento
  setVal("LoopbackVivo", d.loopback_vivo); // Corrigido mapeamento
  setVal("LoopbackCliente", d.loopback_cliente); // Corrigido mapeamento
}

function viewDetails(id) {
  Promise.all([
    fetch(`/prodesp/atendimentos/${id}`).then(r => r.ok ? r.json() : Promise.reject(r.statusText)),
    fetch(`/prodesp/marcos_atividade/${id}`).then(r => r.ok ? r.json() : Promise.reject(r.statusText)),
    fetch(`/prodesp/historico_atendimentos/${id}`).then(r => r.ok ? r.json() : Promise.reject(r.statusText))
  ])
    .then(([d, marcos, historicoRes]) => {
      // Preenche os campos do modal de visualização
      fillModalFields(d, 'view');

      // Renderiza Observações (somente leitura)
      const obsContainer = document.getElementById("log-observacao-view");
      obsContainer.innerHTML = '<div class="titles-incident"><span>DATA</span><span>OBSERVAÇÕES</span></div>';
      if (d.observacoes && d.observacoes.length > 0) {
        d.observacoes.forEach(obs => {
          const card = document.createElement("div");
          card.classList.add("card-incident");
          card.innerHTML = `
            <div class="fields">
              <div class="incident-data">${obs.timestamp || '-'}</div>
              <div class="incident-chamado">${obs.texto || '-'}</div>
            </div>`;
          obsContainer.appendChild(card);
        });
      } else {
        obsContainer.innerHTML += '<div class="text-muted p-2">Nenhuma observação.</div>';
      }

      // Renderiza Equipamentos (somente leitura)
      const eqContainer = document.getElementById("log-equipamento-view");
      eqContainer.innerHTML = '<div class="titles-incident"><span>MODELO</span><span>SERIAL</span><span>VERSÃO</span><span>DESCRIÇÃO</span></div>';
      if (d.equipamentos && d.equipamentos.length > 0) {
        d.equipamentos.forEach(eq => {
          const row = document.createElement("div");
          row.classList.add("card-incident");
          row.innerHTML = `
            <div class="fields">
              <div class="incident-data">${eq.modelo || '-'}</div>
              <div class="incident-data">${eq.serial || '-'}</div>
              <div class="incident-data">${eq.versao || '-'}</div>
              <div class="incident-data">${eq.descricao || '-'}</div>
            </div>`;
          eqContainer.appendChild(row);
        });
      } else {
        eqContainer.innerHTML += '<div class="text-muted p-2">Nenhum equipamento.</div>';
      }

      // Renderiza Links (somente leitura)
      const lnkContainer = document.getElementById("log-link-view");
      lnkContainer.innerHTML = '<div class="titles-incident"><span>ID LINK</span><span>TIPO</span><span>DESIGNADOR</span><span>OPERADORA</span><span>VLAN</span><span>VELOCIDADE</span><span>IP WAN</span><span>GATEWAY</span><span>MÁSCARA</span><span>PPPOE USER</span><span>PPPOE PASS</span></div>';
      if (d.links && d.links.length > 0) {
        d.links.forEach(lnk => {
          const row = document.createElement("div");
          row.classList.add("card-incident");
          row.innerHTML = `
            <div class="fields">
              <div class="incident-data">${lnk.id_vgr_links || '-'}</div>
              <div class="incident-data">${lnk.tipo_links || '-'}</div>
              <div class="incident-data">${lnk.designador_links || '-'}</div>
              <div class="incident-data">${lnk.operadora_links || '-'}</div>
              <div class="incident-data">${lnk.vlan_links || '-'}</div>
              <div class="incident-data">${lnk.velocidade_links || '-'}</div>
              <div class="incident-data">${lnk.ip_wan_links || '-'}</div>
              <div class="incident-data">${lnk.ip_gateway_links || '-'}</div>
              <div class="incident-data">${lnk.ip_mascara_links || '-'}</div>
              <div class="incident-data">${lnk.pppoe_user_links || '-'}</div>
              <div class="incident-data">${lnk.pppoe_pass_links || '-'}</div>
            </div>`;
          lnkContainer.appendChild(row);
        });
      } else {
        lnkContainer.innerHTML += '<div class="text-muted p-2">Nenhum link.</div>';
      }

      // Renderiza Marcos
      document.getElementById("log-marcos-view").innerHTML = renderMarcos(marcos);

      // Renderiza Histórico
      const historicoContainer = document.getElementById("log-historico-view");
      if (historicoContainer) {
        historicoContainer.innerHTML = renderHistorico(historicoRes.dados, historicoRes.admin_user === 1);
      }

      // Força abertura da primeira aba
      const firstTabEl = document.getElementById("view-dados-unidade-tab");
      if (firstTabEl) bootstrap.Tab.getOrCreateInstance(firstTabEl).show();

      bootstrap.Modal.getOrCreateInstance(document.getElementById("viewModal")).show();
    })
    .catch((err) => {
      console.error("Erro em viewDetails:", err);
      showToast(err.message, "danger");
    });
}

async function editDetails(id) {
  try {
    const response = await fetch(`/prodesp/atendimentos/${id}`);
    if (!response.ok) {
      const errorData = await response.json();
      showToast(errorData.message || "Erro ao carregar atendimento.", "danger");
      return;
    }
    const d = await response.json();

    originalData = d; //Salva os dados originais para comparação

    // --- 1. Preenche todos os campos do formulário usando a função auxiliar ---
    fillModalFields(d, 'edit');
    window.limparMotivosSelecionados("edit");
    try {
      await window.carregarMotivosForaPadrao("edit");
      motivosForaPadraoOriginalEdit = await window.marcarMotivosAtendimento("edit", id);
    } catch (motivosErr) {
      console.error("Erro ao carregar motivos fora do padrão:", motivosErr);
      motivosForaPadraoOriginalEdit = [];
    }

    // --- 2. Determina a editabilidade do formulário com base no status e na data ---
    const SUBSTATUS_ESPECIAIS = [];
    const isEditable = true; // Já validamos acima

    setAllEditFieldsDisabled(false);

    // --- 3. Aplica a lógica de UI (listeners) ---
    const statusSelect = document.getElementById("editStatus");
    const substatusSelect = document.getElementById("editSubstatus");
    const analistaInput = document.getElementById("editAnalistaAtuante");
    const btnSave = document.getElementById("btnSalvar");
    const editFormEl = document.getElementById("editForm");

    // Limpa listeners antigos para evitar duplicação
    if (statusSelect._editChangeListener)
      statusSelect.removeEventListener("change", statusSelect._editChangeListener);
    if (editFormEl._inputListener)
      editFormEl.removeEventListener("input", editFormEl._inputListener);

    // Define o estado GERAL do formulário
    btnSave.disabled = false;

    // Configura os listeners para comportamento dinâmico.
    // Listener para habilitar o botão Salvar e acionar o auto-save.
    editFormEl._inputListener = function (event) {
      btnSave.disabled = false;
      const currentStatus = document.getElementById("editStatus").value;
      const finalStatuses = ["Concluído", "Quebra", "Concluida - entrega parcial"];
      if (!finalStatuses.includes(currentStatus)) {
        clearTimeout(autoSaveEditTimeout);
        autoSaveEditTimeout = setTimeout(() => autoSaveEditModalData(false), 2000);
      }
    };
    editFormEl.addEventListener("input", editFormEl._inputListener);

    // Lógica de "Assumir" o atendimento ao abrir o modal.
    const takeoverStatuses = [
      "Em Atendimento",
      "Quebra",
      "Concluído Parcial",
      "Concluído",
    ];
    // APENAS assume se o campo estiver vazio.
    if (
      takeoverStatuses.includes(d.status_atendimento) &&
      (!d.analista_atuante || d.analista_atuante.trim() === "")
    ) {
      analistaInput.value = USUARIO_LOGADO;
    }

    // Listener de MUDANÇA DE STATUS para controlar a UI de campos específicos (substatus, analista).
    statusSelect._editChangeListener = function () {
      const novoStatus = this.value;
      const oldStatus = originalData.status_atendimento;
      const finalStatuses = ["Concluído", "Quebra", "Concluído Parcial"];
      const id = +document.getElementById("editAtendimentoId").value;
      const analistaInput = document.getElementById("editAnalistaAtuante");
      const substatusSelect = document.getElementById("editSubstatus");

      // Popula o substatus com base no novo status
      populateSubstatus(substatusSelect, novoStatus, substatusSelect.value, undefined, undefined, 'edit');

      // ==================================================================
      // Validação prévia ao selecionar status final
      // ==================================================================
      if (finalStatuses.includes(novoStatus)) {
        const validationRules = [
          { id: 'editSubstatus', name: 'Substatus' },
          { id: 'editAnalistaAtuante', name: 'Analista Atuante' },
          { id: 'editContratada', name: 'Contratada' },
          { id: 'editField', name: 'Field' },
          { id: 'editContatoField', name: 'Contato Field' },
        ];

        // Executa a validação aprimorada que destaca campos e accordions
        const emptyFields = validateFields(validationRules);

        if (emptyFields.length > 0) {
          showToast(`Atenção: Para finalizar com este status, os seguintes campos são necessários: ${emptyFields.join(', ')}.`, 'info');
        }
      }

      // Lógica para preencher analista de triagem se estiver vazio e status for de atuação
      const takeoverStatuses = ["Em Atendimento", "Quebra", "Concluído Parcial", "Concluído"];
      if (takeoverStatuses.includes(novoStatus) && (!analistaInput.value || analistaInput.value.trim() === "")) {
        analistaInput.value = USUARIO_LOGADO;
      }

      // Garante que todos os campos de analista permaneçam bloqueados para edição manual
      ["editAnalistaAtuante", "editAnalistaConfiguracao", "editAnalistaMplsAtendimentos", "editAnalistaCadernoTeste"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.readOnly = true;
      });
    };
    statusSelect.addEventListener("change", statusSelect._editChangeListener);

    // Listener para o campo Substatus no Modal de Edição para permitir progressão dinâmica
    if (substatusSelect._editSubstatusChangeListener)
      substatusSelect.removeEventListener("change", substatusSelect._editSubstatusChangeListener);

    let lastModalSubstatus = d.substatus_atendimento;

    substatusSelect._editSubstatusChangeListener = function () {
      const novoSub = this.value;
      const orderedProgression = ["Triagem", "Aguardando Config. Remota", "Em Configuração Remota", "Aguardando Config. MPLS", "Em Configuração do MPLS", "Aguardando Caderno de Teste", "Em Caderno de Teste"];

      const oldIdx = orderedProgression.indexOf(lastModalSubstatus);
      const newIdx = orderedProgression.indexOf(novoSub);

      // Regra: Se mudar para um substatus anterior, apaga os analistas correspondentes que ficaram para trás
      if (newIdx !== -1 && oldIdx !== -1 && newIdx < oldIdx) {
        const analystFields = [
          { idx: 2, id: "editAnalistaConfiguracao" },
          { idx: 4, id: "editAnalistaMplsAtendimentos" },
          { idx: 6, id: "editAnalistaCadernoTeste" }
        ];

        analystFields.forEach(field => {
          if (field.idx > newIdx) {
            const el = document.getElementById(field.id);
            if (el) el.value = "";
          }
        });
      }

      lastModalSubstatus = novoSub;
      populateSubstatus(this, statusSelect.value, novoSub, undefined, undefined, 'edit');
    };
    substatusSelect.addEventListener("change", substatusSelect._editSubstatusChangeListener);


    // Dispara o evento 'change' para configurar o estado inicial dos campos dependentes
    statusSelect.dispatchEvent(new Event("change"));

    // --- 4. Recarrega listas de observações e equipamentos ---
    reloadObservacoes(d.observacoes);
    reloadEquipamentos(d.equipamentos);
    reloadLinks(d.links);

    // Força abertura da primeira aba
    const firstTabEl = document.getElementById("edit-dados-unidade-conectividade-tab");
    if (firstTabEl) bootstrap.Tab.getOrCreateInstance(firstTabEl).show();

    // --- 5. Exibe o modal ---
    bootstrap.Modal.getOrCreateInstance(
      document.getElementById("editModal")
    ).show();
  } catch (err) {
    console.error("Erro em editDetails:", err);
    showToast(err.message, "danger");
  }
}


function pascalize(s) {
  return s
    .split(/[_\-]/)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join("");
}

function idFor(prefix, col) {
  const customMap = { 'id_intragov': 'Idintragov' };
  const suffix = customMap[col] || pascalize(col);
  return prefix + suffix;
}


/**
/**
 * Valida um conjunto de campos de formulário e gerencia a UI do Accordion.
 * @param {Array<Object>} rules - Um array de objetos, onde cada objeto define uma regra de validação. Ex: {id: 'createNome', name: 'Nome da Unidade'}
 * @returns {Array<string>} - Um array com os nomes dos campos inválidos.
 */
function validateFields(rules) {
  const emptyFields = [];
  let firstInvalidTab = null;
  let firstInvalidAccordionPanel = null;

  // 1. Limpa a validação anterior de todos os campos e headers do accordion
  rules.forEach(rule => {
    const el = document.getElementById(rule.id);
    if (el) {
      el.classList.remove('is-invalid');
      // Clean up tab buttons if we add invalid class to them
      const tabPane = el.closest('.tab-pane');
      if (tabPane) {
        const tabId = tabPane.id;
        const tabButton = document.querySelector(`button[data-bs-target="#${tabId}"]`);
        if (tabButton) tabButton.classList.remove('is-invalid', 'text-danger');
      }
      const accordionItem = el.closest('.accordion-item');
      if (accordionItem) {
        const accordionButton = accordionItem.querySelector('.accordion-button');
        if (accordionButton) {
          accordionButton.classList.remove('is-invalid');
        }
      }
    }
  });

  // 2. Itera sobre as regras para encontrar campos inválidos
  for (const rule of rules) {
    const el = document.getElementById(rule.id);

    // A validação checa se o elemento existe e se seu valor está vazio ou se é um select com a opção 'disabled' selecionada.
    if (el && (!el.value || el.value.trim() === '' || (el.tagName === 'SELECT' && el.options[el.selectedIndex].disabled))) {
      emptyFields.push(rule.name);
      el.classList.add('is-invalid'); // Destaca o campo

      // Handle Tabs
      const tabPane = el.closest('.tab-pane');
      if (tabPane && !firstInvalidTab) {
        firstInvalidTab = tabPane;
      }
      if (tabPane) {
        const tabId = tabPane.id;
        const tabButton = document.querySelector(`button[data-bs-target="#${tabId}"]`);
        if (tabButton) tabButton.classList.add('text-danger'); // Visual cue
      }

      // Encontra o accordion pai e o destaca também
      const accordionItem = el.closest('.accordion-item');
      if (accordionItem) {
        const accordionButton = accordionItem.querySelector('.accordion-button');
        const accordionPanel = accordionItem.querySelector('.accordion-collapse');

        if (accordionButton) {
          accordionButton.classList.add('is-invalid');
        }

        // Armazena o primeiro painel inválido para abri-lo depois
        if (accordionPanel && !firstInvalidAccordionPanel) {
          firstInvalidAccordionPanel = accordionPanel;
        }
      }
    }
  }

  // 3. Switch to invalid tab/accordion
  if (firstInvalidTab) {
    const tabId = firstInvalidTab.id;
    const tabButton = document.querySelector(`button[data-bs-target="#${tabId}"]`);
    if (tabButton) {
      const tab = new bootstrap.Tab(tabButton);
      tab.show();
    }
  } else if (firstInvalidAccordionPanel) {
    const bsCollapse = new bootstrap.Collapse(firstInvalidAccordionPanel, {
      toggle: false // Garante que apenas vamos mostrar, não alternar
    });
    bsCollapse.show();
  }

  return emptyFields; // Retorna a lista de nomes de campos para a mensagem de toast
}

async function saveEdit() {
  const saveButton = document.getElementById('btnSalvar');
  setButtonLoading(saveButton, true, 'Salvando...');

  try {
    const id = +document.getElementById("editAtendimentoId").value;
    if (!id) {
      showToast("ID do atendimento não encontrado.", "danger");
      return;
    }

    const statusValue = document.getElementById("editStatus").value;
    const substatusValue = document.getElementById("editSubstatus").value;
    const finalStatuses = ["Concluído", "Quebra", "Concluído Parcial"];
    const isFinalizing = finalStatuses.includes(statusValue);
    const motivosForaPadrao = window.coletarMotivosSelecionados("edit");
    // --- Validações antes de salvar ---
    if (isFinalizing) {
      const validationRules = [
        { id: 'editStatus', name: 'Status' },
        { id: 'editSubstatus', name: 'Substatus' },
        { id: 'editAnalistaAtuante', name: 'Analista Atuante' },
        { id: 'editContratada', name: 'Contratada' },
        { id: 'editField', name: 'Field' },
        { id: 'editContatoField', name: 'Contato Field' },
        { id: 'editIdVgr', name: 'ID VGR' },
        { id: 'editAcronimo', name: 'Acrônimo' },
        { id: 'editHostname', name: 'Hostname' },
        { id: 'editEndereco', name: 'Endereço' },
        { id: 'editNumero', name: 'N°' },
        { id: 'editBairro', name: 'Bairro' },
        { id: 'editMunicipio', name: 'Município' },
        { id: 'editEstado', name: 'Estado' },
        { id: 'editCep', name: 'CEP' },
        { id: 'editLatitude', name: 'Latitude' },
        { id: 'editLongitude', name: 'Longitude' },
        { id: 'editTelefoneContato', name: 'Telefone Contato' }
      ];


      const emptyFields = validateFields(validationRules);

      if (emptyFields.length > 0) {
        showToast(`Para finalizar, preencha os campos obrigatórios: ${emptyFields.join(', ')}.`, 'warning');
        return;
      }
    }

    // --- Coleta de atualizações --- 
    const updates = [];
    const jsFields = [
      "status",
      "substatus",
      "analista_atuante",
      "analista_configuracao",
      "analista_mpls_atendimentos",
      "analista_caderno_teste",
      "contratada",
      "field",
      "contato_field",
      "logs",
      "nome",
      "acronimo",
      "hostname",
      "endereco",
      "numero",
      "bairro",
      "municipio",
      "estado",
      "complemento",
      "data_agendamento",
      "hora_agendamento",
      "cep",
      "latitude",
      "longitude",
      "telefone_contato",
      "ip_lan_01",
      "ip_lan_02",
      "id_intragov",
      "loopback_vivo",
      "loopback_cliente",
    ];
    const keyMap = {
      status: "status_atendimento",
      substatus: "substatus_atendimento",
      analista_atuante: "analista_atuante",
      analista_configuracao: "analista_configuracao",
      analista_mpls_atendimentos: "analista_mpls_atendimentos",
      analista_caderno_teste: "analista_caderno_teste_atendimentos",
      contratada: "contratada",
      field: "field_responsavel",
      contato_field: "contato_field",
      logs: "logs_atendimento",
      nome: "nome",
      acronimo: "acronimo_unidades",
      hostname: "hostname_unidades",
      endereco: "endereco_unidades",
      numero: "numero_unidades",
      bairro: "bairro_unidades",
      municipio: "municipio_unidades",
      estado: "estado_unidades",
      complemento: "complemento_unidades",
      data_agendamento: "data_agendamento_unidades",
      hora_agendamento: "hora_agendamento_unidades",
      cep: "cep_unidades",
      latitude: "latitude_unidades",
      longitude: "longitude_unidades",
      telefone_contato: "telefone_contato_unidades",
      ip_lan_01: "ip_lan_01_unidades",
      ip_lan_02: "ip_lan_02_unidades",
      ip_lan_transito: "ip_lan_transito_unidades",
      id_intragov: "id_intragov_unidades",
      loopback_vivo: "loopback_vivo_unidades",
      loopback_cliente: "loopback_cliente_unidades",
    };

    jsFields.forEach((col) => {
      let novo;
      if (col === "logs") {
        novo = logsEdit.map(l => `[${l.timestamp}] ${l.user}: ${l.text}`).join('\n');
      } else {
        const el = document.getElementById(idFor("edit", col));
        if (!el) return;
        novo = maskInstances[el.id] ? maskInstances[el.id].unmaskedValue : el.value;
      }

      // Previne envio de string vazia para campos de data, hora ou coordenadas
      if (novo === "" && ["data_agendamento", "hora_agendamento", "latitude", "longitude"].includes(col)) {
        novo = null;
      }

      const originalKey = keyMap[col];
      if (originalKey && novo !== (originalData[originalKey] || "").toString()) {
        updates.push({ coluna: col, valor: novo });
      }
    });

    const motivosAlterados = !window.arraysIguaisNumeros(motivosForaPadrao, motivosForaPadraoOriginalEdit);

    if (updates.length === 0 && !motivosAlterados && newObservacao.length === 0 && newEquipamentoEdit.length === 0 && newLinksEdit.length === 0 && deletedObservacaoIds.length === 0 && deletedEquipamentoIds.length === 0 && deletedLinkIds.length === 0) {
      showToast("Nenhuma alteração para salvar.", "info");
      return;
    }

    // --- Processo de salvamento em etapas ---
    let allSuccess = true;

    if (updates.length > 0 || motivosAlterados) {
      const response = await fetch("/prodesp/atendimentos/update", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, updates, motivos_fora_padrao: motivosForaPadrao, finalizing: isFinalizing }),
      });
      const resp = await response.json();
      if (!resp.success) {
        showToast("Erro ao salvar dados principais: " + resp.message, "danger");
        allSuccess = false;
      } else {
        motivosForaPadraoOriginalEdit = [...motivosForaPadrao];
      }
    }

    if (allSuccess && (newObservacao.length > 0 || deletedObservacaoIds.length > 0)) {
      const respObs = await fetch("/prodesp/observacoes-update", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          new_observacoes: newObservacao,
          deleted_observacoes: deletedObservacaoIds
        }),
      }).then((r) => r.json());
      if (!respObs.success) {
        showToast("Erro ao salvar observações: " + respObs.message, "danger");
        allSuccess = false;
      }
    }

    if (allSuccess && (newEquipamentoEdit.length > 0 || deletedEquipamentoIds.length > 0)) {
      const respEq = await fetch("/prodesp/equipamentos-update", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          id_unidade_equipamentos: originalData.id_unidades_atendimentos,
          new_equipamentos: newEquipamentoEdit,
          deleted_equipamentos: deletedEquipamentoIds,
        }),
      }).then((r) => r.json());
      if (!respEq.success) {
        showToast("Erro ao salvar equipamentos: " + respEq.message, "danger");
        allSuccess = false;
      }
    }

    if (allSuccess && (newLinksEdit.length > 0 || deletedLinkIds.length > 0)) {
      const respLnk = await fetch("/prodesp/links-update", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_atendimento: id,
          id_unidade_links: originalData.id_unidades_atendimentos,
          new_links: newLinksEdit,
          deleted_links: deletedLinkIds,
        }),
      }).then((r) => r.json());
      if (!respLnk.success) {
        showToast("Erro ao salvar links: " + respLnk.message, "danger");
        allSuccess = false;
      }
    }

    // --- Finalização ---
    if (allSuccess) {
      showToast("Dados salvos com sucesso!", "success");
      bootstrap.Modal.getInstance(document.getElementById("editModal")).hide();
      location.reload();
    } else {
      showToast("Ocorreram erros ao salvar. Verifique os dados e tente novamente.", "danger");
    }
  } finally {
    setButtonLoading(saveButton, false); // Garante que o botão seja reativado
  }
}

// ------------------------------
// REFERÊNCIAS GLOBAIS
// ------------------------------

const createIdVgrEl = document.getElementById("createIdVgr");
const createForm = document.getElementById("createForm");
const createStatusEl = document.getElementById("createStatus");
const createSubstatusEl = document.getElementById("createSubstatus");
let selectedUnidadeId = null;
let currentCreateModalAtendimentoId = null;
const btnCreateIncident = document.getElementById("btnCreateIncident");
const logConfiguracaoRemotaEdit = document.getElementById("log-configuracao-remota-edit");
const logConfiguracaoRemotaCreate = document.getElementById("log-configuracao-remota-create");

// This variable is not used anywhere else, can be removed.
let originalCreateStatusOptions;

// -------------------------------------------------------------------------------
// FUNÇÃO DE LIMPEZA DOS CAMPOS DA UNIDADE
// -------------------------------------------------------------------------------

function setCreateModalFieldsDisabled(isDisabled) {
  const form = document.getElementById("createForm");
  const elements = form.querySelectorAll("input, select, textarea");
  elements.forEach((el) => {
    // Desabilita todos os campos por padrão, permitindo que o ID VGR seja preenchido
    if (el.id !== "createIdVgr") {
      // Garante que o campo de descrição de equipamento seja sempre apenas leitura
      if (el.id === "createEquipamentoDescricao") {
        el.readOnly = true;
        el.disabled = isDisabled; // Segue o estado de bloqueio geral do formulário
      } else {
        el.disabled = isDisabled;
      }
    }
  });

  // Controla os botões de ação e adição de itens do formulário de criação
  const actionButtonIds = [
    "btn-add-log-create",
    "btn-add-observacao-create",
    "btn-add-equipamento-create",
    "btn-confirm-equipamento-create",
    "btn-cancel-equipamento-create",
    "btn-add-link-create",
    "btn-confirm-link-create",
    "btn-cancel-link-create",
    "btnCreateIncident"
  ];

  actionButtonIds.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = isDisabled;
  });

  // Bloqueia/Desbloqueia botões dentro das listas renderizadas (Equipamentos, Links, Observações, Logs)
  const listContainers = ["log-equipamento-create", "log-link-create", "log-observacao-create", "log-configuracao-remota-create"];
  listContainers.forEach(containerId => {
    const container = document.getElementById(containerId);
    if (container) {
      const internalButtons = container.querySelectorAll("button");
      internalButtons.forEach(btn => btn.disabled = isDisabled);
    }
  });
}

function clearCreateUnidadeFields() {
  [
    "createNome",
    "createAcronimo",
    "createHostname",
    "createEndereco",
    "createNumero",
    "createComplemento",
    "createBairro",
    "createMunicipio",
    "createEstado",
    "createDataAgendamento",
    "createHoraAgendamento",
    "createCep",
    "createLatitude",
    "createLongitude",
    "createTelefoneContato",
    "createIpLan01",
    "createIpLan02",
    "createIdintragov",
    // These are not in the clear list, but should be.
    // 'createLoopbackVivo', 'createLoopbackCliente'
    "createLoopbackVivo",
    "createLoopbackCliente",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  selectedUnidadeId = null;
}

// -------------------------------------------------------------------------------
// PRÉ‑CARREGA UNIDADE QUANDO ID VGR É PREENCHIDO
// -------------------------------------------------------------------------------
if (createIdVgrEl) {
  createIdVgrEl.addEventListener("blur", async () => {
    const idVgr = createIdVgrEl.value.trim();
    if (!idVgr) {
      // Se limpar o campo, volta ao estado de bloqueio total
      setCreateModalFieldsDisabled(true);
      return;
    }

    try {
      // 1. Validar se a unidade existe e buscar seus dados (campos, equipamentos e links)
      const unidadeResponse = await fetch(`/prodesp/unidades/${encodeURIComponent(idVgr)}`);
      const json = await unidadeResponse.json();

      if (!json.success) {
        // Bloqueio se não encontrar o ID VGR na base de unidades
        showToast("ID VGR não encontrado na base de dados. Por favor, realize o upload das informações via CSV - Inserção em Massa.", "danger");
        setCreateModalFieldsDisabled(true); // Re-disables all except ID VGR
        if (createStatusEl) {
          createStatusEl.disabled = true;
          createStatusEl.value = "";
        }
        clearCreateUnidadeFields();
        selectedUnidadeId = null;
        return;
      }

      // Unidade encontrada: popula as informações básicas e os equipamentos/links
      const u = json.unidade;
      selectedUnidadeId = u.id_unidade;

      document.getElementById("createNome").value = u.nome || "";
      document.getElementById("createAcronimo").value = u.acronimo || "";
      document.getElementById("createHostname").value = u.hostname || "";
      document.getElementById("createEndereco").value = u.endereco || "";
      document.getElementById("createNumero").value = u.numero || "";
      document.getElementById("createComplemento").value = u.complemento || "";
      document.getElementById("createBairro").value = u.bairro || "";
      document.getElementById("createMunicipio").value = u.municipio || "";
      document.getElementById("createEstado").value = u.estado || "";
      document.getElementById("createDataAgendamento").value = u.data_agendamento || "";
      document.getElementById("createHoraAgendamento").value = u.hora_agendamento || "";
      document.getElementById("createCep").value = u.cep || "";
      if (maskInstances.createLatitude) maskInstances.createLatitude.value = String(u.latitude || '');
      if (maskInstances.createLongitude) maskInstances.createLongitude.value = String(u.longitude || '');
      document.getElementById("createTelefoneContato").value = u.telefone_contato || "";
      document.getElementById("createIpLan01").value = u.ip_lan_01 || "";
      document.getElementById("createIpLan02").value = u.ip_lan_02 || "";
      document.getElementById("createIpLanTransito").value = u.ip_lan_transito || "";
      document.getElementById("createIdintragov").value = u.id_intragov || "";
      document.getElementById("createLoopbackVivo").value = u.loopback_vivo || "";
      document.getElementById("createLoopbackCliente").value = u.loopback_cliente || "";

      // Carrega Equipamentos e Links vindos do banco para a UI do modal de criação
      reloadEquipamentos(u.equipamentos, 'create');
      reloadLinks(u.links, 'create');

      // ID VGR encontrado: Desbloqueia APENAS o campo de status para iniciar o atendimento
      if (createStatusEl) createStatusEl.disabled = false;

      // 2. Verificar histórico de atendimentos (Redirecionamento ou Avisos)
      const checkResponse = await fetch(`/prodesp/atendimentos/verificar_id_vgr/${encodeURIComponent(idVgr)}`);
      const checkData = await checkResponse.json();

      if (checkData.aviso) {
        if (checkData.action_type === "redirect_edit") {
          showToast(checkData.mensagem, "info");
          bootstrap.Modal.getInstance(document.getElementById("createModal")).hide();
          setTimeout(() => editDetails(checkData.atendimento_id), 500);
          return;
        }

        if (checkData.action_type === "block_creation") {
          showToast(checkData.mensagem, "danger");
          setCreateModalFieldsDisabled(true);
          if (createStatusEl) createStatusEl.disabled = true;
          return;
        }

        if (checkData.action_type === "warn_and_continue") {
          showToast(checkData.mensagem, "warning");
          
          // Observações carregadas do atendimento anterior:
          if (checkData.previous_observacoes && checkData.previous_observacoes.length > 0) {
            const obsContainer = document.getElementById('log-observacao-create');
            if (obsContainer) {
              const obsTitle = document.createElement('p');
              obsTitle.className = 'text-muted fst-italic mt-2';
              obsTitle.textContent = 'Observações carregadas do atendimento anterior:';
              obsContainer.insertBefore(obsTitle, obsContainer.querySelector('.titles-incident'));

              checkData.previous_observacoes.forEach(obs => {
                if (!newObservacaoCreate.some(o => o.observacao_prodesp === obs.observacao_prodesp)) {
                  newObservacaoCreate.push(obs);
                  renderObservacaoCard(obs, obsContainer, newObservacaoCreate, null, true);
                }
              });
            }
          }
        }
      }
    } catch (err) {
      console.error("Erro no fluxo de validação do ID VGR:", err);
      showToast("Ocorreu um erro ao processar os dados do ID VGR.", "danger");
    }
  });
}

// -----------------------------------------------------------------------------------
// ABRE O MODAL DE CRIAÇÃO
// -----------------------------------------------------------------------------------
function openCreateModal() {
  createForm.reset();
  clearCreateUnidadeFields();
  newObservacaoCreate.length = 0;
  newEquipamentoCreate.length = 0;
  newLinksCreate.length = 0;
  // Reset editing states
  editingEquipmentId = null;
  existingEquipmentsCreate.length = 0;
  existingLinksCreate.length = 0;
  currentCreateModalAtendimentoId = null;
  window.limparMotivosSelecionados("create");

  // Estado inicial: a maioria dos campos e botões desabilitados
  setCreateModalFieldsDisabled(true);
  if (createIdVgrEl) createIdVgrEl.disabled = false; // Habilita apenas o campo ID VGR

  const createAnalistaAtuanteEl = document.getElementById(
    "createAnalistaAtuante"
  );
  if (createAnalistaAtuanteEl) {
    createAnalistaAtuanteEl.value = USUARIO_LOGADO;
    createAnalistaAtuanteEl.readOnly = true;
  }

  ["createAnalistaConfiguracao", "createAnalistaMplsAtendimentos", "createAnalistaCadernoTeste"].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.value = "";
      el.readOnly = true;
    }
  });

  // Popula o campo Status com apenas a opção inicial
  if (createStatusEl) {
    createStatusEl.innerHTML = '<option selected disabled value="">Selecione o status...</option>';
    createStatusEl.add(new Option("Em Atendimento", "Em Atendimento"));
  }
  // Garante que o Substatus comece desabilitado e limpo
  const substatusEl = document.getElementById("createSubstatus");
  if (substatusEl) {
    substatusEl.innerHTML =
      '<option selected disabled value="">Selecione o Substatus...</option>';
    substatusEl.disabled = true;
  }

  if (btnCreateIncident) btnCreateIncident.textContent = "Criar";

  if (logContainerObservacaoCreate && observacaoCreateHeaderHtml) {
    // Ensure the header is present before setting innerHTML
    if (!logContainerObservacaoCreate.querySelector('.titles-incident')) {
        logContainerObservacaoCreate.innerHTML = observacaoCreateHeaderHtml;
    }
    logContainerObservacaoCreate.innerHTML = observacaoCreateHeaderHtml;
  }
  if (logContainerEquipamentoCreate) {
    logContainerEquipamentoCreate.innerHTML = equipamentoCreateHeaderHtml;
  }
  if (logContainerLinkCreate) {
    logContainerLinkCreate.innerHTML = linkCreateHeaderHtml;
  }

  window.carregarMotivosForaPadrao("create").catch(err => {
    console.error("Erro ao carregar motivos fora do padrão:", err);
  });

  // Reset button states for equipment and links
  toggleEditButtons('create', false);

  // Força abertura da primeira aba
  const firstTabEl = document.getElementById("create-dados-unidade-conectividade-tab");
  if (firstTabEl) bootstrap.Tab.getOrCreateInstance(firstTabEl).show();

  bootstrap.Modal.getOrCreateInstance(
    document.getElementById("createModal")
  ).show();
}

window.openCreateModal = openCreateModal;

function getCreateModalData() {
  return {
    status: document.getElementById("createStatus").value,
    substatus: document.getElementById("createSubstatus").value,
    analista_atuante: document.getElementById("createAnalistaAtuante").value,
    analista_configuracao: document.getElementById("createAnalistaConfiguracao").value,
      analista_mpls_atendimentos: document.getElementById("createAnalistaMplsAtendimentos").value,
    analista_caderno_teste: document.getElementById("createAnalistaCadernoTeste").value,
    contratada: document.getElementById("createContratada").value,
    field: document.getElementById("createField").value,
    contato_field: document.getElementById("createContatoField").value.replace(/\D/g, ''),
    numero: document.getElementById("createNumero").value,
    nome: document.getElementById("createNome").value,
    data_agendamento: document.getElementById("createDataAgendamento").value,
    hora_agendamento: document.getElementById("createHoraAgendamento").value,
    motivos_fora_padrao: coletarMotivosSelecionados("create"),
  };
}
function getSanitizedValue(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return null;

  if (
    el.tagName === "SELECT" &&
    el.options[el.selectedIndex] &&
    el.options[el.selectedIndex].disabled
  ) {
    return null;
  }
  return el.value || null;
}

if (createStatusEl) {
  // Listener para o campo Status no Modal de Criação
  createStatusEl.addEventListener("change", async function () {
    const statusValue = this.value;
    const idVgrValue = document.getElementById("createIdVgr").value.trim();
    const substatusEl = document.getElementById("createSubstatus");
    const finalStatusesForValidation = ["Concluído", "Quebra", "Concluído Parcial"];

    if (finalStatusesForValidation.includes(statusValue)) {
      // Regras de validação para finalização
      const validationRules = [
        { id: 'createSubstatus', name: 'Substatus' },
        { id: 'createField', name: 'Field' },
        { id: 'createContatoField', name: 'Contato Field' },
        { id: 'createContratada', name: 'Contratada' },
      ];

      // Executa a validação aprimorada que destaca campos e accordions
      const emptyFields = validateFields(validationRules);

      if (emptyFields.length > 0) {
        showToast(`Para usar o status '${statusValue}', preencha os campos obrigatórios: ${emptyFields.join(', ')}.`, 'warning');
      }
    }

    if (finalStatusesForValidation.includes(statusValue)) {
      // Aciona o auto-save diretamente se um atendimento já foi iniciado
      if (currentCreateModalAtendimentoId) {
        clearTimeout(autoSaveTimeout);
        autoSaveTimeout = setTimeout(autoSaveCreateModalData, 500);
      }
    }

    // Lógica para popular dinamicamente o Substatus
    if (substatusEl) {
      populateSubstatus(substatusEl, statusValue, substatusEl.value, undefined, undefined, 'create');
    }

    if (
      !selectedUnidadeId && !idVgrValue &&
      (statusValue === "Em Atendimento")
    ) {
      showToast("Por favor, preencha o ID VGR e selecione uma unidade antes de definir o status.", "warning");
      this.value = ""; // Redefine status de seleção
      return;
    }

    let payload;

    if (statusValue === "Em Atendimento") {
      // Inicia atendimento com status "Em Atendimento"
      setCreateModalFieldsDisabled(false);
      if (!currentCreateModalAtendimentoId) {
        payload = {
          status: statusValue,
          id_vgr: idVgrValue,
          id_unidade: selectedUnidadeId,
          analista_atuante: document.getElementById("createAnalistaAtuante").value,
          analista_configuracao: document.getElementById("createAnalistaConfiguracao").value,
          analista_mpls_atendimentos: document.getElementById("createAnalistaMplsAtendimentos").value,
          analista_caderno_teste: document.getElementById("createAnalistaCadernoTeste").value,
          substatus: getSanitizedValue("createSubstatus"),
          contratada: getSanitizedValue("createContratada"),
          logs: logsCreate.map(l => `[${l.timestamp}] ${l.user}: ${l.text}`).join('\n'),
          field: getSanitizedValue("createField"),
          contato_field: getSanitizedValue("createContatoField"),
          nome: getSanitizedValue("createNome"),
          acronimo: getSanitizedValue("createAcronimo"),
          hostname: getSanitizedValue("createHostname"),
          endereco: getSanitizedValue("createEndereco"),
          numero: getSanitizedValue("createNumero"),
          complemento: getSanitizedValue("createComplemento"),
          bairro: getSanitizedValue("createBairro"),
          municipio: getSanitizedValue("createMunicipio"),
          estado: getSanitizedValue("createEstado"),
          data_agendamento: getSanitizedValue("createDataAgendamento"),
          hora_agendamento: getSanitizedValue("createHoraAgendamento"),
          latitude: maskInstances.createLatitude ? maskInstances.createLatitude.unmaskedValue : getSanitizedValue("createLatitude"),
          longitude: maskInstances.createLongitude ? maskInstances.createLongitude.unmaskedValue : getSanitizedValue("createLongitude"),
          cep: getSanitizedValue("createCep"),
          telefone_contato: getSanitizedValue("createTelefoneContato"),
          ip_lan: getSanitizedValue("createIpLan"),
          id_intragov: getSanitizedValue("createIdintragov"),
          loopback_vivo: getSanitizedValue("createLoopbackVivo"),
          loopback_cliente: getSanitizedValue("createLoopbackCliente"),
          new_observacoes: newObservacaoCreate,
          new_equipamentos: newEquipamentoCreate,
          new_links: newLinksCreate,
        };

        try {
          const res = await fetch("/prodesp/atendimentos/create", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const result = await res.json();
          if (result.success) {
            currentCreateModalAtendimentoId = result.id;
            if (result.id_unidade) selectedUnidadeId = result.id_unidade;
            if (btnCreateIncident)
              btnCreateIncident.textContent = "Salvar Atendimento";
            showToast(`Atendimento iniciado com sucesso. ID: ${result.id}`, "success");

            createStatusEl.innerHTML = '<option selected disabled value="">Selecione o status...</option>'; // Mantém o placeholder
            createStatusEl.add(new Option("Em Atendimento", "Em Atendimento"));
            createStatusEl.add(new Option("Quebra", "Quebra"));
            createStatusEl.add(new Option("Concluído", "Concluído"));
            createStatusEl.add(new Option("Concluído Parcial", "Concluído Parcial"));
            createStatusEl.value = statusValue;

            newObservacaoCreate.length = 0;
            newEquipamentoCreate.length = 0;
            newLinksCreate.length = 0;
          } else {
            showToast(`Erro ao iniciar atendimento: ${result.message}`, "danger");
            this.value = "";
          }
        } catch (err) {
          showToast(`Erro de comunicação ao criar atendimento: ${err}`, "danger");
          this.value = "";
        }
      } else {
        await autoSaveCreateModalData();
        showToast("Status atualizado para EM ATENDIMENTO.", "success");
      }
    } else {
      if (currentCreateModalAtendimentoId) {
        await autoSaveCreateModalData();
        setCreateModalFieldsDisabled(false);
      } else {
        setCreateModalFieldsDisabled(true);
      }
    }
  });
}

if (createSubstatusEl) {
  // Listener para o campo Substatus no Modal de Criação para permitir progressão dinâmica
  createSubstatusEl.addEventListener("change", function () {
    populateSubstatus(this, createStatusEl.value, this.value, undefined, undefined, 'create');
  });
}


// ---------------------------------------------------------------------------------
// FUNÇÃO PARA AUTO-SALVAR DADOS NO MODAL DE CRIAÇÃO
// ---------------------------------------------------------------------------------
let autoSaveTimeout = null; // Global variable for debounce timeout

async function autoSaveCreateModalData() {
  if (!currentCreateModalAtendimentoId) {
    console.warn("Attempted auto-save without an existing attendance ID.");
    return;
  }

  const updates = [];
  const payloadForLists = {
    // Dados necessários para observações e atualizações de equipamentos
    id_atendimento: currentCreateModalAtendimentoId,
    id_unidade_equipamentos: selectedUnidadeId,
    new_observacoes: newObservacaoCreate,
    new_equipamentos: newEquipamentoCreate,
    new_links: newLinksCreate,
  };

  // Coletar todos os dados atuais do formulário para os principais campos da Unidade
  const currentFormData = getCreateModalData(); // Gets status, substatus, etc.
  const motivosForaPadrao = currentFormData.motivos_fora_padrao || [];
  delete currentFormData.motivos_fora_padrao;
  const unidadeFormData = {
    nome: document.getElementById("createNome").value,
    acronimo: document.getElementById("createAcronimo").value,
    hostname: document.getElementById("createHostname").value,
    endereco: document.getElementById("createEndereco").value,
    numero: document.getElementById("createNumero").value,
    complemento: document.getElementById("createComplemento").value,
    bairro: document.getElementById("createBairro").value,
    municipio: document.getElementById("createMunicipio").value,
    estado: document.getElementById("createEstado").value,
    data_agendamento: document.getElementById("createDataAgendamento").value,
    hora_agendamento: document.getElementById("createHoraAgendamento").value,
    cep: document.getElementById("createCep").value,
    latitude: maskInstances.createLatitude ? maskInstances.createLatitude.unmaskedValue : document.getElementById("createLatitude").value,
    longitude: maskInstances.createLongitude ? maskInstances.createLongitude.unmaskedValue : document.getElementById("createLongitude").value,
    telefone_contato: document.getElementById("createTelefoneContato").value,
    ip_lan_01: document.getElementById("createIpLan01").value,
    ip_lan_02: document.getElementById("createIpLan02").value,
    ip_lan_transito: document.getElementById("createIpLanTransito").value,
    id_intragov: document.getElementById("createIdintragov").value,
    loopback_vivo: document.getElementById("createLoopbackVivo").value,
    loopback_cliente: document.getElementById("createLoopbackCliente").value,
  };

  // Combine todos os dados em um único objeto para a chamada de atualização principal
  const combinedData = { ...currentFormData, ...unidadeFormData };

  for (const key in combinedData) {
    if (key === "motivos_fora_padrao") continue;
    let val = combinedData[key];
    if (key === 'logs') {
      val = logsCreate.map(l => `[${l.timestamp}] ${l.user}: ${l.text}`).join('\n');
    } else if (typeof val === 'string') {
      val = val.trim();
    }
    updates.push({ coluna: key, valor: val });
  }

  let allSuccess = true;

  // 1. Atualiza dados principais
  if (updates.length > 0 || motivosForaPadrao.length >= 0) {
    try {
      const resMain = await fetch("/prodesp/atendimentos/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: currentCreateModalAtendimentoId,
          updates: updates,
          motivos_fora_padrao: motivosForaPadrao,
          finalizing: false,
        }),
      });
      const resultMain = await resMain.json();
      if (!resultMain.success) {
        console.error("Auto-save: Erro ao atualizar dados principais: " + resultMain.message);
        allSuccess = false;
      }
    } catch (err) {
      console.error("Auto-save: Falha ao atualizar dados principais.", err);
      allSuccess = false;
    }
  }

  // 2. Salva novas observações
  if (payloadForLists.new_observacoes.length > 0) {
    const observationsToSave = [...newObservacaoCreate];
    newObservacaoCreate.length = 0;

    try {
      const respObs = await fetch("/prodesp/observacoes-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...payloadForLists,
          new_observacoes: observationsToSave,
        }),
      });
      const resultObs = await respObs.json();
      if (!resultObs.success) {
        console.error("Auto-save: Erro ao salvar novas observações: " + resultObs.message);
        newObservacaoCreate.push(...observationsToSave);
        allSuccess = false;
      }
    } catch (err) {
      console.error("Auto-save: Falha ao salvar novas observações.", err);
      newObservacaoCreate.push(...observationsToSave);
      allSuccess = false;
    }
  }

  // 3. Save new equipments
  if (payloadForLists.new_equipamentos.length > 0) {
    const equipmentsToSave = [...newEquipamentoCreate];
    newEquipamentoCreate.length = 0;

    try {
      const respEq = await fetch("/prodesp/equipamentos-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...payloadForLists,
          new_equipamentos: equipmentsToSave,
        }),
      });
      const resultEq = await respEq.json();
      if (!resultEq.success) {
        console.error("Auto-save: Erro ao salvar novos equipamentos: " + resultEq.message);
        newEquipamentoCreate.push(...equipmentsToSave);
        allSuccess = false;
      }
    } catch (err) {
      console.error("Auto-save: Falha ao salvar novos equipamentos.", err);
      newEquipamentoCreate.push(...equipmentsToSave);
      allSuccess = false;
    }
  }

  // 4. Save new links
  if (payloadForLists.new_links.length > 0) {
    const linksToSave = [...newLinksCreate];
    newLinksCreate.length = 0;

    try {
      const respLnk = await fetch("/prodesp/links-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_unidade_links: selectedUnidadeId,
          new_links: linksToSave,
        }),
      });
      const resultLnk = await respLnk.json();
      if (!resultLnk.success) {
        console.error("Auto-save: Erro ao salvar novos links: " + resultLnk.message);
        newLinksCreate.push(...linksToSave);
        allSuccess = false;
      }
    } catch (err) {
      console.error("Auto-save: Falha ao salvar novos links.", err);
      newLinksCreate.push(...linksToSave);
      allSuccess = false;
    }
  }

  if (allSuccess) {
    console.log("Auto-save completo para atendimento ID:", currentCreateModalAtendimentoId);
  } else {
    console.error("Auto-save falhou para atendimento ID:", currentCreateModalAtendimentoId);
  }
}

// Adicionar eventos para salvamento automático
if (createForm) {
  createForm.addEventListener("input", function (event) {
    if (currentCreateModalAtendimentoId) {
      clearTimeout(autoSaveTimeout);
      autoSaveTimeout = setTimeout(async () => {
        await autoSaveCreateModalData();
      }, 2000);
    }
  });

  createForm.addEventListener("change", function (event) {
    if (currentCreateModalAtendimentoId) {
      clearTimeout(autoSaveTimeout);
      autoSaveTimeout = setTimeout(async () => {
        await autoSaveCreateModalData();
      }, 500);
    }
  });
}

// ------------------------------------------------------------------
// SALVA NOVO ATENDIMENTO
// ------------------------------------------------------------------
async function handleCreateModalSave() {

  const statusValue = document.getElementById('createStatus').value;
  const substatusValue = document.getElementById('createSubstatus').value;
  const finalStatuses = ["Concluído", "Quebra", "Concluído Parcial"];
  const isFinalizing = finalStatuses.includes(statusValue);
  const motivosForaPadrao = coletarMotivosSelecionados("create");



  const validationRules = [
    { id: 'createStatus', name: 'Status' },
    { id: 'createSubstatus', name: 'Substatus' },
    { id: 'createAnalistaAtuante', name: 'Analista Atuante' },
    { id: 'createContratada', name: 'Contratada' },
    { id: 'createField', name: 'Field' },
    { id: 'createContatoField', name: 'Contato Field' },
    { id: 'createIdVgr', name: 'ID VGR' },
    { id: 'createAcronimo', name: 'Acrônimo' },
    { id: 'createHostname', name: 'Hostname' },
    { id: 'createEndereco', name: 'Endereço' },
    { id: 'createNumero', name: 'N°' },
    { id: 'createBairro', name: 'Bairro' },
    { id: 'createMunicipio', name: 'Município' },
    { id: 'createEstado', name: 'Estado' },
    { id: 'createCep', name: 'CEP' },
    { id: 'createLatitude', name: 'Latitude' },
    { id: 'createLongitude', name: 'Longitude' },
    { id: 'createTelefoneContato', name: 'Telefone Contato' }
  ];


  const emptyFields = validateFields(validationRules);

  if (emptyFields.length > 0) {
    return showToast(`Campos obrigatórios não preenchidos: ${emptyFields.join(', ')}.`, 'warning');
  }

  if (currentCreateModalAtendimentoId) {
    // Este é o caminho de FINALIZAÇÃO.
    let allSuccess = true;
    const updates = [];
    const payload = {
      ...getCreateModalData(),
      nome: document.getElementById("createNome").value,
      acronimo: document.getElementById("createAcronimo").value,
      hostname: document.getElementById("createHostname").value,
      endereco: document.getElementById("createEndereco").value,
      bairro: document.getElementById("createBairro").value,
      municipio: document.getElementById("createMunicipio").value,
      estado: document.getElementById("createEstado").value,
      complemento: document.getElementById("createComplemento").value,
      data_agendamento: document.getElementById("createDataAgendamento").value,
      hora_agendamento: document.getElementById("createHoraAgendamento").value,
      ip_lan_01: document.getElementById("createIpLan01").value,
      ip_lan_02: document.getElementById("createIpLan02").value,
      ip_lan_transito: document.getElementById("createIpLanTransito").value,
      id_intragov: document.getElementById("createIdintragov").value,
      telefone_contato: document.getElementById("createTelefoneContato").value.replace(/\D/g, ''),
      cep: document.getElementById("createCep").value,
      latitude: maskInstances.createLatitude ? maskInstances.createLatitude.unmaskedValue : document.getElementById("createLatitude").value,
      longitude: maskInstances.createLongitude ? maskInstances.createLongitude.unmaskedValue : document.getElementById("createLongitude").value,
    };

    const fieldsToUpdate = [
      "status",
      "substatus",
      "analista_atuante",
      "analista_configuracao",
      "analista_mpls_atendimentos",
      "analista_caderno_teste",
      "contratada",
      "field",
      "contato_field",
      "logs",
      "nome",
      "acronimo",
      "hostname",
      "endereco",
      "bairro",
      "municipio",
      "estado",
      "complemento",
      "data_agendamento",
      "hora_agendamento",
      "ip_lan_01",
      "ip_lan_02",
      "ip_lan_transito",
      "id_intragov",
      "telefone_contato",
      "cep",
      "latitude",
      "longitude",
      "loopback_vivo",
      "loopback_cliente"
    ];

    fieldsToUpdate.forEach(key => {
      if (key === "logs") {
        updates.push({ coluna: key, valor: logsCreate.map(l => `[${l.timestamp}] ${l.user}: ${l.text}`).join('\n') });
      } else if (payload.hasOwnProperty(key) && payload[key] !== null && payload[key] !== undefined) {
        updates.push({ coluna: key, valor: payload[key] });
      }
    });

    // ETAPA 1: Atualizar os dados principais.
    if (updates.length > 0) {
      try {
        const resMain = await fetch("/prodesp/atendimentos/update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id: currentCreateModalAtendimentoId,
            updates: updates,
            motivos_fora_padrao: motivosForaPadrao,
            finalizing: true,
          }),
        });
        const resultMain = await resMain.json();
        if (!resultMain.success) {
          showToast("Erro ao atualizar dados principais: " + resultMain.message, "danger");
          allSuccess = false;
        }
      } catch (err) {
        showToast("Falha ao atualizar dados principais. Verifique a conexão e os dados inseridos.", "danger");
        console.error("Erro em fetch /prodesp/atendimentos/update:", err);
        allSuccess = false;
      }
    }

    // ETAPA 2: Adicionar novas observações.
    if (allSuccess && newObservacaoCreate.length > 0) {
      try {
        const respObs = await fetch("/prodesp/observacoes-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_atendimento: currentCreateModalAtendimentoId,
            new_observacoes: newObservacaoCreate,
            deleted_observacoes: [],
          }),
        }).then((r) => r.json());
        if (!respObs.success) {
          showToast("Erro ao salvar novas observações: " + respObs.message, "danger");
          allSuccess = false;
        }
      } catch (err) {
        showToast("Falha de comunicação ao salvar novas observações.", "danger");
        allSuccess = false;
      }
    }

    // ETAPA 3: Adicionar novos equipamentos.
    if (allSuccess && newEquipamentoCreate.length > 0) {
      try {
        const respEq = await fetch("/prodesp/equipamentos-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_unidade_equipamentos: selectedUnidadeId,
            new_equipamentos: newEquipamentoCreate,
            deleted_equipamentos: [],
          }),
        }).then((r) => r.json());
        if (!respEq.success) {
          showToast("Erro ao salvar novos equipamentos: " + respEq.message, "danger");
          allSuccess = false;
        }
      } catch (err) {
        showToast("Falha de comunicação ao salvar novos equipamentos.", "danger");
        allSuccess = false;
      }
    }

    // ETAPA 4: Adicionar novos links.
    if (allSuccess && newLinksCreate.length > 0) {
      try {
        const respLnk = await fetch("/prodesp/links-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_unidade_links: selectedUnidadeId,
            new_links: newLinksCreate,
            deleted_links: [],
          }),
        }).then((r) => r.json());
        if (!respLnk.success) {
          showToast("Erro ao salvar novos links: " + respLnk.message, "danger");
          allSuccess = false;
        }
      } catch (err) {
        showToast("Falha de comunicação ao salvar novos links.", "danger");
        allSuccess = false;
      }
    }

    // FINALIZAÇÃO
    if (allSuccess) {
      showToast("Atendimento Salvo com sucesso!", "success");
      bootstrap.Modal.getInstance(document.getElementById("createModal")).hide();
      location.reload();
    }
  } else {
    // Este é o caminho de CRIAÇÃO inicial.
    const payload = {
      id_unidade: selectedUnidadeId,
      ...getCreateModalData(),
      id_vgr: document.getElementById("createIdVgr").value.trim(),
      nome: document.getElementById("createNome").value,
      acronimo: document.getElementById("createAcronimo").value,
      hostname: document.getElementById("createHostname").value,
      endereco: document.getElementById("createEndereco").value,
      bairro: document.getElementById("createBairro").value,
      municipio: document.getElementById("createMunicipio").value,
      estado: document.getElementById("createEstado").value,
      complemento: document.getElementById("createComplemento").value,
      data_agendamento: document.getElementById("createDataAgendamento").value,
      hora_agendamento: document.getElementById("createHoraAgendamento").value,
      ip_lan_01: document.getElementById("createIpLan01").value,
      ip_lan_02: document.getElementById("createIpLan02").value,
      ip_lan_transito: document.getElementById("createIpLanTransito").value,
      id_intragov: document.getElementById("createIdintragov").value,
      cep: document.getElementById("createCep").value,
      latitude: maskInstances.createLatitude ? maskInstances.createLatitude.unmaskedValue : document.getElementById("createLatitude").value,
      longitude: maskInstances.createLongitude ? maskInstances.createLongitude.unmaskedValue : document.getElementById("createLongitude").value,
      telefone_contato: document.getElementById("createTelefoneContato").value.replace(/\D/g, ''),
      loopback_vivo: document.getElementById("createLoopbackVivo").value,
      loopback_cliente: document.getElementById("createLoopbackCliente").value,
      logs: logsCreate.map(l => `[${l.timestamp}] ${l.user}: ${l.text}`).join('\n'),
      new_observacoes: newObservacaoCreate,
      new_equipamentos: newEquipamentoCreate,
      new_links: newLinksCreate,
    };
    try {
      const res = await fetch("/prodesp/atendimentos/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.message);
      showToast("Atendimento criado com sucesso: " + data.id, "success");
      bootstrap.Modal.getInstance(document.getElementById("createModal")).hide();
      editingEquipmentId = null; // Reset editing state
      editingLinkId = null;     // Reset editing state
      location.reload();
    } catch (err) {
      console.error("Erro ao criar atendimento:", err);
      showToast("Erro ao criar atendimento: " + err.message, "danger");
    }
  }
}
window.handleCreateModalSave = handleCreateModalSave;

// ----------------------------------------------------------------------------------------
// VARIÁVEIS GLOBAIS PARA OBSERVAÇÕES EDIÇÃO
// ----------------------------------------------------------------------------------------
const newObservacao = [];
const deletedObservacaoIds = [];
const newEquipamentoEdit = [];
const deletedEquipamentoIds = [];
const newLinksEdit = [];
const deletedLinkIds = [];
let logsEdit = [];
let logsCreate = [];

// ---------------------------------------------------------------------------------------
// VARIÁVEIS GLOBAIS PARA OBSERVAÇÕES CRIAÇÃO
// ---------------------------------------------------------------------------------------
const newObservacaoCreate = [];

// ---------------------------------------------------------------------------------------
// ELEMENTOS DO DOM PARA OBSERVAÇÕES - EDIÇÃO
// ---------------------------------------------------------------------------------------
const logContainerObservacao = document.querySelector("#log-observacao-edit");
const observacaoHeader = logContainerObservacao ? logContainerObservacao.querySelector(".titles-incident") : null;
const observacaoHeaderHtml = observacaoHeader ? observacaoHeader.outerHTML : "";

const observacaoEl = document.getElementById("editObservacaoTexto");
const btnAddObservacao = document.getElementById("btn-add-observacao-edit");
const btnSave = document.getElementById("btnSalvar");

// ---------------------------------------------------------------------------------------
// ELEMENTOS DO DOM PARA OBSERVAÇÕES - CRIAÇÃO 
// ---------------------------------------------------------------------------------------
const logContainerObservacaoCreate = document.querySelector("#log-observacao-create");
const observacaoCreateHeader = logContainerObservacaoCreate ? logContainerObservacaoCreate.querySelector(".titles-incident") : null;
const observacaoCreateHeaderHtml = observacaoCreateHeader ? observacaoCreateHeader.outerHTML : "";

const observacaoCreateEl = document.getElementById("createObservacaoTexto");
const btnAddObservacaoCreate = document.getElementById("btn-add-observacao-create");

// --------------------------------------------------------------------------------
// FUNÇÕES DE OBSERVAÇÕES
// --------------------------------------------------------------------------------
// Função genérica para renderizar um card de observação
// Recebe o objeto da observação, o container onde ela será adicionada
// e a lista de observações à qual ela pertence (para remoção)
function renderObservacaoCard(
  observacaoObj,
  containerEl,
  targetArray,
  deletedArray = null
) {
  if (!containerEl) {
    console.error("Container de log não encontrado para renderizar card.", containerEl);
    return;
  }

  const card = document.createElement("div");
  card.classList.add("card-incident");
  const fields = document.createElement("div");
  fields.classList.add("fields");

  const makeDiv = (cls, txt) => {
    const d = document.createElement("div");
    d.classList.add(cls);
    d.style.whiteSpace = "pre-wrap"; // Preserva quebras de linha e espaços
    d.textContent = txt || "—";
    return d;
  };

  fields.appendChild(makeDiv("incident-data", observacaoObj.data_observacao));
  fields.appendChild(makeDiv("incident-chamado", observacaoObj.observacao_prodesp));

  const delButton = document.createElement("button");
  delButton.textContent = "🗑️";
  delButton.type = "button";
  delButton.classList.add("btn", "btn-sm", "btn-outline-danger", "ms-2"); // Adicionei algumas classes Bootstrap para melhor visual

  delButton.addEventListener("click", () => {
    card.remove(); // Remove o card visualmente do DOM

    // Lógica para remover do array correto
    if (observacaoObj.id_observacao && deletedArray) {
      // Se tem ID do banco e há array de deletados (edição)
      deletedArray.push(observacaoObj.id_observacao);
    }

    const idx = targetArray.indexOf(observacaoObj);
    if (idx > -1) {
      targetArray.splice(idx, 1); // Remove do array de origem
    }
  });

  // Bloqueio se for modal de criação e atendimento não iniciado
  if (containerEl && containerEl.id.includes('create') && !currentCreateModalAtendimentoId) {
    delButton.disabled = true;
  }

  card.appendChild(fields);
  card.appendChild(delButton);
  containerEl.appendChild(card);
}

// --- Lógica de Adição de Observações ---

// Adicionar Observação - MODAL DE EDIÇÃO
if (btnAddObservacao) {
  // Verifica se o botão existe antes de adicionar o listener
  btnAddObservacao.addEventListener("click", () => {
    const agora = new Date();
    const fmt2 = (n) => String(n).padStart(2, "0");
    const dataHora = fmt2(agora.getDate()) + "/" + fmt2(agora.getMonth() + 1) + "/" + agora.getFullYear() + " " + fmt2(agora.getHours()) + ":" + fmt2(agora.getMinutes()) + ":" + fmt2(agora.getSeconds());
    const observacaoText = observacaoEl ? observacaoEl.value.trim() : ""; // Pega o valor do input de edição

    if (!observacaoText) {
      return showToast(
        "Preencha o campo de observação do modal de edição.",
        "warning"
      );
    }

    const observacaoObj = {
      data_observacao: dataHora,
      observacao_prodesp: observacaoText,
    };

    // Impede duplicação exata
    if (
      newObservacao.some(
        (x) =>
          x.data_observacao === observacaoObj.data_observacao &&
          x.observacao_prodesp === observacaoObj.observacao_prodesp
      )
    ) {
      return showToast(
        "Esta observação já foi adicionada na edição.",
        "warning"
      );
    }

    newObservacao.push(observacaoObj);
    renderObservacaoCard(
      observacaoObj,
      logContainerObservacao,
      newObservacao,
      deletedObservacaoIds
    ); // Passa os arrays corretos
    if (observacaoEl) observacaoEl.value = ""; // Limpa o input
    // if (btnSave) btnSave.disabled = false; // Habilita o botão salvar
  });
} else {
  console.warn("Botão 'btn-add-observacao-edit' não encontrado. Verifique seu HTML.");
}

// Adicionar Observação - MODAL DE CRIAÇÃO
if (btnAddObservacaoCreate) {
  // Verifica se o botão existe antes de adicionar o listener
  btnAddObservacaoCreate.addEventListener("click", () => {
    const agora = new Date();
    const fmt2 = (n) => String(n).padStart(2, "0");
    const dataHora = fmt2(agora.getDate()) + "/" + fmt2(agora.getMonth() + 1) + "/" + agora.getFullYear() + " " + fmt2(agora.getHours()) + ":" + fmt2(agora.getMinutes()) + ":" + fmt2(agora.getSeconds());
    const observacaoText = observacaoCreateEl ? observacaoCreateEl.value.trim() : ""; // Pega o valor do input de criação
    if (!observacaoText) {
      return showToast(
        "Preencha o campo de observação do modal de criação.",
        "warning"
      );
    }

    const observacaoObj = {
      data_observacao: dataHora,
      observacao_prodesp: observacaoText,
    };

    // Impede duplicação exata
    if (
      newObservacaoCreate.some(
        (x) =>
          x.data_observacao === observacaoObj.data_observacao &&
          x.observacao_prodesp === observacaoObj.observacao_prodesp
      )
    ) {
      return showToast(
        "Esta observação já foi adicionada na criação.",
        "warning"
      );
    }

    newObservacaoCreate.push(observacaoObj);
    renderObservacaoCard(
      observacaoObj,
      logContainerObservacaoCreate,
      newObservacaoCreate,
      null
    );
    if (observacaoCreateEl) observacaoCreateEl.value = ""; // Limpa o input
    // btnSave.disabled = false; // Este botão é para o modal de edição, não aplica aqui
  });
} else {
  console.warn(
    "Botão 'btn-add-observacao-create' não encontrado. Verifique seu HTML."
  );
}

// --- Funções de Limpeza e Recarregamento (Foco na Edição) ---

// Limpa observações QUANDO FECHA O MODAL DE EDIÇÃO
const modalEl = document.getElementById("editModal");
if (modalEl) {
  modalEl.addEventListener("hide.bs.modal", () => {
    // Redefine o conteúdo do container de observações para o cabeçalho inicial
    if (logContainerObservacao) {
      logContainerObservacao.innerHTML = observacaoHeaderHtml;
    }
    newObservacao.length = 0;
    deletedObservacaoIds.length = 0;
    // if (btnSave) btnSave.disabled = true; // Desabilita ao fechar 
    if (observacaoEl) observacaoEl.value = ""; // Limpa o input de observação

    // Limpa a busca URL com o INEP do atendimento que foi redirecionado 
    // This logic seems specific to FUST project, not Prodesp.
    // It also reloads the page, which might not be desired if only clearing URL params.
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has("search_id_vgr")) {
      urlParams.delete("search_id_vgr");
      const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
      window.history.replaceState({}, document.title, newUrl);
      location.reload();
    }

    if (logConfiguracaoRemotaEdit) {
        const header = logConfiguracaoRemotaEdit.querySelector(".titles-incident");
        if (header) {
            logConfiguracaoRemotaEdit.innerHTML = header.outerHTML;
        }
    }
  });
}

// --- Lógica para o Modal de Criação (Limpeza) ---

// Limpa observações QUANDO FECHA O MODAL DE CRIAÇÃO
const createModalEl = document.getElementById("createModal");
if (createModalEl) {
  createModalEl.addEventListener("hide.bs.modal", () => {
    if (logContainerObservacaoCreate) {
      logContainerObservacaoCreate.innerHTML = observacaoCreateHeaderHtml ||
        '<div class="titles-incident"><span>DATA</span><span>OBSERVAÇÕES</span><span></span></div>'; // Fallback header
    }
    newObservacaoCreate.length = 0; // Limpa o array de novas observações do modal de criação
    if (observacaoCreateEl) observacaoCreateEl.value = ""; // Limpa o input de observação

    // Reset other create modal specific things
    currentCreateModalAtendimentoId = null;
    setCreateModalFieldsDisabled(false); // Re-enable all fields
    if (createForm) createForm.reset();
    clearCreateUnidadeFields();
    if (logContainerEquipamentoCreate) {
      logContainerEquipamentoCreate.innerHTML = equipamentoCreateHeaderHtml;
    }
    newEquipamentoCreate.length = 0;
    if (logContainerLinkCreate) {
      logContainerLinkCreate.innerHTML = linkCreateHeaderHtml;
    }
    newLinksCreate.length = 0;

    // Reset editing states for create modal
    editingEquipmentId = null;
    editingLinkId = null;
    toggleEditButtons('create', false);
    if (logConfiguracaoRemotaCreate) {
      const header = logConfiguracaoRemotaCreate.querySelector(".titles-incident");
      if (header) {
          logConfiguracaoRemotaCreate.innerHTML = header.outerHTML;
      }
    }
    if (btnCreateIncident) btnCreateIncident.textContent = "Criar";
  });
}

// ------------------------------
// VARIÁVEIS GLOBAIS PARA EQUIPAMENTOS EDIÇÃO
// ------------------------------
// ------------------------------
// VARIÁVEIS GLOBAIS PARA EQUIPAMENTOS CRIAÇÃO
// ------------------------------
const newEquipamentoCreate = [];
const newLinksCreate = [];
const existingEquipmentsCreate = []; // Para armazenar equipamentos de atendimentos anteriores para validação de duplicatas

// ------------------------------
// ELEMENTOS DO DOM PARA EQUIPAMENTOS - EDIÇÃO
// ------------------------------
const logContainerEquipamentoEdit = document.querySelector("#log-equipamento-edit");
const equipamentoEditHeader = logContainerEquipamentoEdit ? logContainerEquipamentoEdit.querySelector(".titles-incident") : null;
const equipamentoEditHeaderHtml = equipamentoEditHeader ? equipamentoEditHeader.outerHTML : "";
const logContainerLinkEdit = document.querySelector("#log-link-edit");
const linkEditHeader = logContainerLinkEdit ? logContainerLinkEdit.querySelector(".titles-incident") : null;
const linkEditHeaderHtml = linkEditHeader ? linkEditHeader.outerHTML : "";

const equipamentoModeloEditEl = document.getElementById("editEquipamentoModelo");
const equipamentoSerialEditEl = document.getElementById("editEquipamentoSerial");
const equipamentoVersaoEditEl = document.getElementById("editEquipamentoVersao");
const equipamentoMacEditEl = document.getElementById("editEquipamentoMac"); // Assuming MAC field exists
const equipamentoIotEditEl = document.getElementById("editEquipamentoIot"); // Assuming IoT field exists
const equipamentoDescricaoEditEl = document.getElementById("editEquipamentoDescricao");
// Removed btnAddEquipamentoEdit as it's now dynamically controlled
const btnAddLinkEdit = document.getElementById("btn-add-link-edit");

// -----------------------------------------------------------------------------------
// ELEMENTOS DO DOM PARA EQUIPAMENTOS - CRIAÇÃO
// -----------------------------------------------------------------------------------
const logContainerEquipamentoCreate = document.querySelector("#log-equipamento-create");
const equipamentoCreateHeader = logContainerEquipamentoCreate ? logContainerEquipamentoCreate.querySelector(".titles-incident") : null;
const equipamentoCreateHeaderHtml = equipamentoCreateHeader ? equipamentoCreateHeader.outerHTML : "";
const logContainerLinkCreate = document.querySelector("#log-link-create");
const linkCreateHeader = logContainerLinkCreate ? logContainerLinkCreate.querySelector(".titles-incident") : null;
// Missing linkCreateHeaderHtml definition
// const linkCreateHeaderHtml = linkCreateHeader ? linkCreateHeader.outerHTML : "";
const linkCreateHeaderHtml = linkCreateHeader ? linkCreateHeader.outerHTML : "";
const equipamentoModeloCreateEl = document.getElementById("createEquipamentoModelo");
const equipamentoSerialCreateEl = document.getElementById("createEquipamentoSerial");
const equipamentoVersaoCreateEl = document.getElementById("createEquipamentoVersao");
const equipamentoDescricaoCreateEl = document.getElementById("createEquipamentoDescricao");
const btnAddEquipamentoCreate = document.getElementById("btn-add-equipamento-create");

// --------------------------------------------------------------------------------
// FUNÇÕES AUXILIARES PARA EQUIPAMENTOS
// --------------------------------------------------------------------------------

// Helper function to manage equipment button visibility
function toggleEditButtons(context, isEditing) {
    const addBtn = document.getElementById(`btn-add-equipamento-${context}`);
    const confirmBtn = document.getElementById(`btn-confirm-equipamento-${context}`);
    const cancelBtn = document.getElementById(`btn-cancel-equipamento-${context}`);

    if (addBtn) addBtn.classList.toggle('d-none', isEditing);
    if (confirmBtn) confirmBtn.classList.toggle('d-none', !isEditing);
    if (cancelBtn) cancelBtn.classList.toggle('d-none', !isEditing);

    // Desabilita/Habilita o botão de adicionar link. 
    // No contexto de criação, só habilita se o atendimento já foi iniciado.
    const addLinkBtn = document.getElementById(`btn-add-link-${context}`);
    if (addLinkBtn) {
        addLinkBtn.disabled = isEditing || (context === 'create' && !currentCreateModalAtendimentoId);
    }
}

// Helper function to manage link button visibility
function toggleEditLinkButtons(context, isEditing) {
    const addBtn = document.getElementById(`btn-add-link-${context}`);
    const confirmBtn = document.getElementById(`btn-confirm-link-${context}`);
    const cancelBtn = document.getElementById(`btn-cancel-link-${context}`);

    if (addBtn) addBtn.classList.toggle('d-none', isEditing);
    if (confirmBtn) confirmBtn.classList.toggle('d-none', !isEditing);
    if (cancelBtn) cancelBtn.classList.toggle('d-none', !isEditing);

    // Desabilita/Habilita o botão de adicionar equipamento.
    // No contexto de criação, só habilita se o atendimento já foi iniciado.
    const addEquipBtn = document.getElementById(`btn-add-equipamento-${context}`);
    if (addEquipBtn) {
        addEquipBtn.disabled = isEditing || (context === 'create' && !currentCreateModalAtendimentoId);
    }
}

// Function to clear equipment form fields
function clearEquipmentForm(context) {
    const getEl = (id) => document.getElementById(`${context}${id}`);
    getEl('EquipamentoModelo').value = "";
    getEl('EquipamentoDescricao').value = "";
    getEl('EquipamentoVersao').value = "";
    // Assuming these exist based on context
    const macEl = getEl('EquipamentoMac');
    if (macEl) macEl.value = "";
    const iotEl = getEl('EquipamentoIot');
    if (iotEl) iotEl.checked = false;

    if (maskInstances[`${context}EquipamentoSerial`]) maskInstances[`${context}EquipamentoSerial`].value = ''; else getEl('EquipamentoSerial').value = '';
    // Hide numero field if it was visible
    const numeroWrapper = document.getElementById(`${context}EquipamentoNumeroWrapper`);
    if (numeroWrapper) numeroWrapper.classList.add('d-none');
    const numeroEl = getEl('EquipamentoNumero');
    if (numeroEl) numeroEl.value = '';
}

// Function to clear link form fields
function clearLinkForm(context) {
    const getEl = (id) => document.getElementById(`${context}Link${id}`);
    const fields = ['Designador', 'Tipo', 'Operadora', 'Vlan', 'IpWan', 'IpGateway', 'IpMascara', 'Velocidade', 'PppoeUser', 'PppoePass', 'IdVgr'];
    fields.forEach(f => { const el = getEl(f); if (el) el.value = ""; });
    const typeSelect = getEl('Tipo');
    if (typeSelect) typeSelect.dispatchEvent(new Event('change')); // Trigger change to hide/show conditional fields
}

function cancelEditEquipment(context) {
    editingEquipmentId = null;
    toggleEditButtons(context, false);
    clearEquipmentForm(context);
}

function cancelEditLink(context) {
    editingLinkId = null;
    toggleEditLinkButtons(context, false);
    clearLinkForm(context);
}

// --------------------------------------------------------------------------------
// FUNÇÕES DE EQUIPAMENTOS
// --------------------------------------------------------------------------------

// Função genérica para renderizar um card de equipamento
function renderEquipamentoCard(equipamentoObj, containerEl, targetArray, deletedArray = null, context = 'edit') {
  if (!containerEl) {
    console.error("Container de log de equipamentos não encontrado para renderizar card.", containerEl);
    return;
  }

  const row = document.createElement("div");
  row.classList.add("card-incident");
  const fields = document.createElement("div");
  fields.classList.add("fields");

  const renderViewMode = () => {
    fields.innerHTML = '';
    // Verifica se é um item com erro de coleta (Datacom)
    if ((equipamentoObj.serial && equipamentoObj.serial.includes('Erro'))) {
      row.classList.add('text-danger', 'bg-danger-subtle');
      row.title = "Falha na coleta deste equipamento via SSH. Verifique a conectividade.";
    }

    const makeDiv = (txt) => {
      const d = document.createElement("div");
      d.classList.add("incident-data");
      d.textContent = txt || "—";
      return d;
    };

    const makeCopyableDiv = (txt, copyTitle) => {
      const d = makeDiv(txt);
      if (txt && txt !== '—') {
        const icon = document.createElement('i');
        icon.className = 'far fa-copy btn-copy-inline ms-2 text-muted';
        icon.title = copyTitle;
        icon.style.cursor = 'pointer';
        icon.onclick = (e) => {
          e.stopPropagation();
          navigator.clipboard.writeText(txt).then(() => showToast(`'${txt}' copiado!`, 'success'));
        };
        d.appendChild(icon);
      }
      return d;
    };

    fields.appendChild(makeDiv(equipamentoObj.modelo));
    fields.appendChild(makeCopyableDiv(equipamentoObj.serial, 'Copiar Serial'));
    fields.appendChild(makeDiv(equipamentoObj.versao));
    fields.appendChild(makeDiv(equipamentoObj.descricao));

    actionDiv.innerHTML = '';
    const editButton = document.createElement("button");
    editButton.innerHTML = '<i class="fas fa-pencil-alt"></i>';
    editButton.type = "button";
    editButton.classList.add("btn", "btn-sm", "btn-outline-primary");
    editButton.title = "Editar Equipamento";
    editButton.onclick = () => renderEditMode();

    const delButton = document.createElement("button");
    delButton.innerHTML = '<i class="fas fa-trash"></i>';
    delButton.type = "button";
    delButton.classList.add("btn", "btn-sm", "btn-outline-danger");
    delButton.title = "Excluir Equipamento";
    delButton.onclick = () => deleteEquipment();

    if (context === 'create' && !currentCreateModalAtendimentoId) {
      editButton.disabled = delButton.disabled = true;
    }
    actionDiv.append(editButton, delButton);
  };

  const renderEditMode = () => {
    fields.innerHTML = '';
    const createCell = (content) => {
      const d = document.createElement('div'); d.className = 'incident-data';
      d.appendChild(content); return d;
    };

    const sel = document.createElement('select');
    sel.className = 'form-select form-select-sm';
    ["FortiGate 40F", "FortiGate 60F", "FortiGate 120G", "FortiGate 900G", "FortiGate 3200F", "FortiGate 3700F", "FortiGate 600F", "FortiSwitch 2048F"].forEach(opt => sel.add(new Option(opt, opt)));
    sel.value = equipamentoObj.modelo;

    const serialInp = document.createElement('input');
    serialInp.className = 'form-control form-control-sm';
    serialInp.value = equipamentoObj.serial;
    IMask(serialInp, { mask: /^[a-zA-Z0-9\-]*$/, prepare: str => str.toUpperCase() });

    const versaoInp = document.createElement('input');
    versaoInp.className = 'form-control form-control-sm';
    versaoInp.value = equipamentoObj.versao || "";

    const descInp = document.createElement('input');
    descInp.className = 'form-control form-control-sm';
    descInp.readOnly = true;
    descInp.value = equipamentoObj.descricao || "";

    sel.onchange = () => {
      const val = sel.value;
      const autoDescModels = ["FortiGate 40F", "FortiGate 60F", "FortiGate 120G", "FortiGate 900G", "FortiGate 3200F", "FortiGate 3700F", "FortiGate 600F"];
      descInp.value = autoDescModels.includes(val) ? "Firewall - Stand Alone" : (val === "FortiSwitch 2048F" ? "Switch" : "");
    };

    fields.append(createCell(sel), createCell(serialInp), createCell(versaoInp), createCell(descInp));

    actionDiv.innerHTML = '';
    const saveBtn = document.createElement('button');
    saveBtn.innerHTML = '<i class="fas fa-check"></i>';
    saveBtn.className = 'btn btn-sm btn-success';
    saveBtn.onclick = async () => {
      const modelo = sel.value;
      const serial = serialInp.value.trim().toUpperCase();
      if (!modelo || !serial) return showToast("Modelo e Serial são obrigatórios.", "warning");

      const attendanceId = context === 'edit' ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
      const unitId = context === 'edit' ? originalData.id_unidades_atendimentos : selectedUnidadeId;

      try {
        const res = await fetch("/prodesp/equipamentos-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_atendimento: attendanceId,
            id_unidade_equipamentos: unitId,
            new_equipamentos: [{ id: equipamentoObj.id_equipamento, modelo, serial, versao: versaoInp.value.trim(), descricao: descInp.value }],
            deleted_equipamentos: []
          }),
        });
        const r = await res.json();
        if (r.success) {
          showToast("Equipamento atualizado!", "success");
          const d = await (await fetch(`/prodesp/atendimentos/${attendanceId}`)).json();
          reloadEquipamentos(d.equipamentos, context);
        } else showToast(r.message, "danger");
      } catch (e) { showToast("Erro ao salvar.", "danger"); }
    };

    const cancelBtn = document.createElement('button');
    cancelBtn.innerHTML = '<i class="fas fa-times"></i>';
    cancelBtn.className = 'btn btn-sm btn-secondary';
    cancelBtn.onclick = () => renderViewMode();

    actionDiv.append(saveBtn, cancelBtn);
  };

  const deleteEquipment = async () => {
    if (equipamentoObj.id_equipamento) {
      const attendanceId = context === 'edit' ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
      const unitId = context === 'edit' ? originalData.id_unidades_atendimentos : selectedUnidadeId;

      try {
        const res = await fetch("/prodesp/equipamentos-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_atendimento: attendanceId, 
            id_unidade_equipamentos: unitId,
            new_equipamentos: [],
            deleted_equipamentos: [equipamentoObj.id_equipamento]
          }),
        });
        const result = await res.json();
        if (result.success) {
          row.remove();
          showToast("Equipamento removido do banco.", "success");
        } else {
          showToast(result.message, "danger");
        }
      } catch (e) { showToast("Erro ao excluir equipamento.", "danger"); }
    } else {
      row.remove();
      const idx = targetArray.findIndex(eq => eq.serial === equipamentoObj.serial);
      if (idx > -1) targetArray.splice(idx, 1);
    }
  };

  const actionDiv = document.createElement("div");
  actionDiv.style.display = "flex";
  actionDiv.style.gap = "5px";

  row.append(fields, actionDiv);
  containerEl.appendChild(row);
  renderViewMode();
}

/**
 * Lógica unificada para adicionar um equipamento nos modais de criação ou edição.
 * @param {('create'|'edit')} context - O contexto do modal (criação ou edição).
 */
async function addEquipmentLogic(context) {
  // Mapeia os elementos do DOM com base no contexto
  const getEl = (id) => document.getElementById(`${context}${id}`);
  const elements = {
    modelo: getEl('EquipamentoModelo'),
    serial: getEl('EquipamentoSerial'),
    versao: getEl('EquipamentoVersao'),
    descricao: getEl('EquipamentoDescricao'),
    logContainer: document.getElementById(`log-equipamento-${context}`),
  };

  // Obtém os valores dos campos, aplicando formatação
  const modelo = elements.modelo.value.trim();
  const serial = elements.serial.value.trim().toUpperCase();
  const descricao = elements.descricao.value.trim();
  const versao = elements.versao ? elements.versao.value.trim() : '';
  const equipmentId = editingEquipmentId;

  // Validação de campos obrigatórios
  if (!modelo || !serial) {
    return showToast("Para adicionar um equipamento, Modelo e Serial são obrigatórios.", "warning");
  }

  // Validação local imediata (mesma unidade) - Ignora o ID em edição
  const existingEquipArray = context === 'edit' ? existingEquipments : existingEquipmentsCreate;
  if (existingEquipArray.some(eq => (eq.serial || '').trim().toUpperCase() === serial && eq.id_equipamento !== equipmentId)) {
    return showToast("Este equipamento (Serial) já está adicionado nesta unidade.", "warning");
  }

  const attendanceId = context === 'edit' ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
  const unitId = context === 'edit' ? originalData.id_unidades_atendimentos : selectedUnidadeId;
  if (!attendanceId) return showToast("Inicie o atendimento antes de adicionar itens.", "warning");

  const eqPayload = { modelo, serial, versao, descricao };
  if (equipmentId) eqPayload.id = equipmentId; // Inclui o ID para UPDATE no backend

  try {
    const res = await fetch("/prodesp/equipamentos-update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_atendimento: attendanceId,
        id_unidade_equipamentos: unitId,
        new_equipamentos: [eqPayload],
        deleted_equipamentos: []
      }),
    });
    const result = await res.json();
    if (result.success) {
      showToast(equipmentId ? "Equipamento atualizado!" : "Equipamento adicionado!", "success");
      const detailRes = await fetch(`/prodesp/atendimentos/${attendanceId}`);
      const detailData = await detailRes.json();
      reloadEquipamentos(detailData.equipamentos, context);

      // Reseta o estado da UI
      cancelEditEquipment(context);
    } else {
      showToast(result.message, "danger");
    }
  } catch (err) { showToast("Erro ao salvar equipamento.", "danger"); }
}

// Adiciona os listeners aos botões, chamando a função unificada 
document.getElementById('btn-add-equipamento-edit')?.addEventListener('click', () => addEquipmentLogic('edit'));
document.getElementById('btn-confirm-equipamento-edit')?.addEventListener('click', () => addEquipmentLogic('edit'));
document.getElementById('btn-cancel-equipamento-edit')?.addEventListener('click', () => cancelEditEquipment('edit'));

document.getElementById('btn-add-equipamento-create')?.addEventListener('click', () => addEquipmentLogic('create'));
document.getElementById('btn-confirm-equipamento-create')?.addEventListener('click', () => addEquipmentLogic('create'));
document.getElementById('btn-cancel-equipamento-create')?.addEventListener('click', () => cancelEditEquipment('create'));

// --------------------------------------------------------------------------------
// FUNÇÕES DE LINKS
// --------------------------------------------------------------------------------

function renderLinkCard(linkObj, containerEl, targetArray, deletedArray = null, context = 'edit') {
  if (!containerEl) return;

  const row = document.createElement("div");
  row.classList.add("card-incident");
  const fields = document.createElement("div");
  fields.classList.add("fields");

  const renderViewMode = () => {
    fields.innerHTML = '';
    const makeDiv = (txt) => {
      const d = document.createElement("div");
      d.classList.add("incident-data");
      d.textContent = txt || "—";
      return d;
    };

    fields.appendChild(makeDiv(linkObj.id_vgr));
    fields.appendChild(makeDiv(linkObj.tipo));
    fields.appendChild(makeDiv(linkObj.designador));
    fields.appendChild(makeDiv(linkObj.operadora));
    fields.appendChild(makeDiv(linkObj.vlan));
    fields.appendChild(makeDiv(linkObj.velocidade));
    fields.appendChild(makeDiv(linkObj.ip_wan));
    fields.appendChild(makeDiv(linkObj.ip_gateway));
    fields.appendChild(makeDiv(linkObj.ip_mascara));
    fields.appendChild(makeDiv(linkObj.pppoe_user));
    fields.appendChild(makeDiv(linkObj.pppoe_pass));

    actionDiv.innerHTML = '';
    const editButton = document.createElement("button");
    editButton.innerHTML = '<i class="fas fa-pencil-alt"></i>';
    editButton.type = "button";
    editButton.classList.add("btn", "btn-sm", "btn-outline-primary");
    editButton.title = "Editar Link";
    editButton.onclick = () => renderEditMode();

    const delButton = document.createElement("button");
    delButton.innerHTML = '<i class="fas fa-trash"></i>';
    delButton.type = "button";
    delButton.classList.add("btn", "btn-sm", "btn-outline-danger");
    delButton.title = "Excluir Link";
    delButton.onclick = () => deleteLink();

    if (context === 'create' && !currentCreateModalAtendimentoId) {
      editButton.disabled = delButton.disabled = true;
    }
    actionDiv.append(editButton, delButton);
  };

  const renderEditMode = () => {
    fields.innerHTML = '';
    const createCell = (content) => {
      const d = document.createElement('div'); d.className = 'incident-data';
      d.appendChild(content); return d;
    };

    const idVgrInp = document.createElement('input'); idVgrInp.className = 'form-control form-control-sm'; idVgrInp.value = linkObj.id_vgr || "";
    const typeSel = document.createElement('select'); typeSel.className = 'form-select form-select-sm';
    ["STATIC", "MPLS", "DHCP", "PPPoE"].forEach(opt => typeSel.add(new Option(opt, opt))); typeSel.value = linkObj.tipo || "";
    const desigInp = document.createElement('input'); desigInp.className = 'form-control form-control-sm'; desigInp.value = linkObj.designador || "";
    const operInp = document.createElement('input'); operInp.className = 'form-control form-control-sm'; operInp.value = linkObj.operadora || "";
    const vlanInp = document.createElement('input'); vlanInp.className = 'form-control form-control-sm'; vlanInp.value = linkObj.vlan || "";
    const velInp = document.createElement('input'); velInp.className = 'form-control form-control-sm'; velInp.value = linkObj.velocidade || "";
    const wanInp = document.createElement('input'); wanInp.className = 'form-control form-control-sm'; wanInp.value = linkObj.ip_wan || "";
    const gwInp = document.createElement('input'); gwInp.className = 'form-control form-control-sm'; gwInp.value = linkObj.ip_gateway || "";
    const maskInp = document.createElement('input'); maskInp.className = 'form-control form-control-sm'; maskInp.value = linkObj.ip_mascara || "";
    const uInp = document.createElement('input'); uInp.className = 'form-control form-control-sm'; uInp.value = linkObj.pppoe_user || "";
    const pInp = document.createElement('input'); pInp.className = 'form-control form-control-sm'; pInp.value = linkObj.pppoe_pass || "";

    fields.append(createCell(idVgrInp), createCell(typeSel), createCell(desigInp), createCell(operInp), createCell(vlanInp), createCell(velInp), createCell(wanInp), createCell(gwInp), createCell(maskInp), createCell(uInp), createCell(pInp));

    actionDiv.innerHTML = '';
    const saveBtn = document.createElement('button'); saveBtn.innerHTML = '<i class="fas fa-check"></i>'; saveBtn.className = 'btn btn-sm btn-success';
    saveBtn.onclick = async () => {
      if (!typeSel.value || !desigInp.value.trim()) return showToast("Tipo e Designador são obrigatórios.", "warning");
      const attendanceId = context === 'edit' ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
      const unitId = context === 'edit' ? originalData.id_unidades_atendimentos : selectedUnidadeId;
      try {
        const res = await fetch("/prodesp/links-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_atendimento: attendanceId,
            id_unidade_links: unitId,
            new_links: [{ id: linkObj.id_link, id_vgr: idVgrInp.value.trim(), tipo: typeSel.value, designador: desigInp.value.trim(), operadora: operInp.value.trim(), vlan: vlanInp.value.trim(), velocidade: velInp.value.trim(), ip_wan: wanInp.value.trim(), ip_gateway: gwInp.value.trim(), ip_mascara: maskInp.value.trim(), pppoe_user: uInp.value.trim(), pppoe_pass: pInp.value.trim() }],
            deleted_links: []
          }),
        });
        const r = await res.json();
        if (r.success) {
          showToast("Link atualizado!", "success");
          const d = await (await fetch(`/prodesp/atendimentos/${attendanceId}`)).json();
          reloadLinks(d.links, context);
        } else showToast(r.message, "danger");
      } catch (e) { showToast("Erro ao salvar.", "danger"); }
    };
    const cancelBtn = document.createElement('button'); cancelBtn.innerHTML = '<i class="fas fa-times"></i>'; cancelBtn.className = 'btn btn-sm btn-secondary';
    cancelBtn.onclick = () => renderViewMode();
    actionDiv.append(saveBtn, cancelBtn);
  };

  const deleteLink = async () => {
    if (linkObj.id_link) {
      const attendanceId = context === 'edit' ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
      const unitId = context === 'edit' ? originalData.id_unidades_atendimentos : selectedUnidadeId;
      try {
        const res = await fetch("/prodesp/links-update", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id_atendimento: attendanceId, 
            id_unidade_links: unitId,
            new_links: [],
            deleted_links: [linkObj.id_link]
          }),
        });
        const result = await res.json();
        if (result.success) {
          row.remove();
          showToast("Link removido do banco.", "success");
        } else { showToast(result.message, "danger"); }
      } catch (e) { showToast("Erro ao excluir link.", "danger"); }
    } else {
      row.remove();
      const idx = targetArray.findIndex(l => l.designador === linkObj.designador);
      if (idx > -1) targetArray.splice(idx, 1);
    }
  };

  const actionDiv = document.createElement("div");
  actionDiv.style.display = "flex";
  actionDiv.style.gap = "5px";

  row.append(fields, actionDiv);
  containerEl.appendChild(row);
  renderViewMode();
}

async function addLinkLogic(context) {
  const getEl = (id) => document.getElementById(`${context}Link${id}`);
  const fields = ['Designador', 'Tipo', 'Operadora', 'Vlan', 'IpWan', 'IpGateway', 'IpMascara', 'Velocidade', 'PppoeUser', 'PppoePass', 'IdVgr'];
  const values = {};
  fields.forEach(f => {
    const el = getEl(f);
    values[f] = el ? el.value.trim() : '';
  });

  // Check if 'id' is present for an update operation
  const linkId = editingLinkId;

  if (!values.Tipo) return showToast("O campo Tipo de Link é obrigatório.", "warning");
  if (!values.Designador) return showToast("O campo Designador é obrigatório.", "warning");

  // Validação local imediata (mesma unidade), excluindo o ID em edição
  const existingLnkArray = context === 'edit'
        ? existingLinks
        : existingLinksCreate;
  if (existingLnkArray.some(l => (l.designador || '').trim().toUpperCase() === values.Designador.toUpperCase() && l.id_link !== linkId)) {
    return showToast("Este designador já foi adicionado neste atendimento.", "warning");
  }

  const attendanceId = context === 'edit' ? +document.getElementById("editAtendimentoId").value : currentCreateModalAtendimentoId;
  const unitId = context === 'edit' ? originalData.id_unidades_atendimentos : selectedUnidadeId;
  if (!attendanceId) return showToast("Inicie o atendimento antes de adicionar links.", "warning");

  const idVgrInput = getEl('IdVgr');
  const mainIdVgr = document.getElementById(`${context}IdVgr`).value.trim();

  const linkObj = {
    designador: values.Designador,
    tipo: values.Tipo,
    operadora: values.Operadora,
    vlan: values.Vlan,
    ip_wan: values.IpWan,
    ip_gateway: values.IpGateway,
    ip_mascara: values.IpMascara,
    velocidade: values.Velocidade,
    pppoe_user: values.PppoeUser,
    pppoe_pass: values.PppoePass,
    id_vgr: (idVgrInput && idVgrInput.value.trim()) ? idVgrInput.value.trim() : mainIdVgr,
    id: linkId // Pass the ID for update operations
  };

  try {
    const res = await fetch("/prodesp/links-update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_atendimento: attendanceId,
        id_unidade_links: unitId,
        new_links: [linkObj],
        deleted_links: []
      }),
    });
    const result = await res.json();
    if (result.success) {
      showToast("Link salvo!", "success");
      const detailRes = await fetch(`/prodesp/atendimentos/${attendanceId}`);
      const detailData = await detailRes.json();
      reloadLinks(detailData.links, context);
      
      cancelEditLink(context);
    } else {
      showToast(result.message, "danger");
      return;
    }
  } catch (err) { return showToast("Erro ao conectar ao servidor.", "danger"); }
}

document.getElementById('btn-add-link-edit')?.addEventListener('click', () => addLinkLogic('edit'));
document.getElementById('btn-confirm-link-edit')?.addEventListener('click', () => addLinkLogic('edit'));
document.getElementById('btn-cancel-link-edit')?.addEventListener('click', () => cancelEditLink('edit'));

document.getElementById('btn-add-link-create')?.addEventListener('click', () => addLinkLogic('create'));
document.getElementById('btn-confirm-link-create')?.addEventListener('click', () => addLinkLogic('create'));
document.getElementById('btn-cancel-link-create')?.addEventListener('click', () => cancelEditLink('create'));

// --------------------------------------------------------------------------------
// FUNÇÕES DE LOGS (Adicionar texto ao textarea)
// --------------------------------------------------------------------------------
function parseLogString(logString) {
  if (!logString || typeof logString !== 'string') return [];
  return logString.split('\n').filter(line => line.trim() !== '').map(entry => {
    const match = entry.match(/^\[(.*?)\] (.*?): (.*)$/);
    return match ? { timestamp: match[1], user: match[2], text: match[3] } : { timestamp: '—', user: '—', text: entry };
  });
}

function renderLogCard(logObj, containerEl, targetArray) {
  if (!containerEl) return;
  const card = document.createElement("div");
  card.classList.add("card-incident");
  const fields = document.createElement("div");
  fields.classList.add("fields");
  const makeDiv = (cls, txt) => {
    const d = document.createElement("div");
    d.classList.add(cls);
    d.style.whiteSpace = "pre-wrap"; // Preserva quebras de linha e espaços
    d.textContent = txt || "—";
    return d;
  };
  fields.appendChild(makeDiv("incident-data", logObj.timestamp));
  fields.appendChild(makeDiv("incident-user", logObj.user));
  fields.appendChild(makeDiv("incident-log-text", logObj.text));
  const delButton = document.createElement("button");
  delButton.innerHTML = '<i class="fas fa-trash"></i>';
  delButton.type = "button";
  delButton.classList.add("btn", "btn-sm", "btn-outline-danger", "ms-2");
  delButton.addEventListener("click", () => {
    card.remove();
    const idx = targetArray.indexOf(logObj);
    if (idx > -1) targetArray.splice(idx, 1);
    const context = containerEl.id.includes('edit') ? 'edit' : 'create';
    const form = document.getElementById(`${context}Form`);
    if (form) form.dispatchEvent(new Event('input', { bubbles: true }));
  });

  // Bloqueio se for modal de criação e atendimento não iniciado
  if (containerEl && containerEl.id.includes('create') && !currentCreateModalAtendimentoId) {
    delButton.disabled = true;
  }

  card.appendChild(fields);
  card.appendChild(delButton);
  containerEl.appendChild(card);
}

function reloadLogs(logString, containerEl, context) {
  if (!containerEl) return;
  const logsData = parseLogString(logString);
  const header = containerEl.querySelector(".titles-incident");
  containerEl.innerHTML = header ? header.outerHTML : "";
  const targetArray = (context === 'edit') ? logsEdit : logsCreate;
  targetArray.length = 0;
  logsData.forEach(log => {
    targetArray.push(log);
    renderLogCard(log, containerEl, targetArray);
  });
}

function addLogLogic(context) {
  const inputEl = document.getElementById(`${context}LogInput`);
  const containerEl = document.getElementById(`log-configuracao-remota-${context}`);

  if (!inputEl || !containerEl) return;

  const text = inputEl.value.trim();
  if (!text) {
    return showToast("Digite um texto para adicionar ao log.", "warning");
  }

  const logObj = {
    timestamp: new Date().toLocaleString('pt-BR'),
    user: typeof USUARIO_LOGADO !== 'undefined' ? USUARIO_LOGADO : 'Usuário',
    text: text
  };

  const targetArray = (context === 'edit') ? logsEdit : logsCreate;
  targetArray.push(logObj);
  renderLogCard(logObj, containerEl, targetArray);

  inputEl.value = ""; // Limpa o input

  const form = document.getElementById(`${context}Form`);
  if (form) form.dispatchEvent(new Event('input', { bubbles: true }));
}

document.getElementById('btn-add-log-edit')?.addEventListener('click', () => addLogLogic('edit'));
document.getElementById('btn-add-log-create')?.addEventListener('click', () => addLogLogic('create'));

// -------------------------------------------------
// Funções de Limpeza e Recarregamento (Edição de Equipamentos)
// -------------------------------------------------
// Limpa equipamentos QUANDO FECHA O MODAL DE EDIÇÃO
if (modalEl) {
  modalEl.addEventListener("hide.bs.modal", () => {
    // Reset editing states
    editingEquipmentId = null;
    editingLinkId = null;
    // Lógica de limpeza para equipamentos
    const container = document.getElementById("log-equipamento-edit");
    if (container) container.innerHTML = equipamentoEditHeaderHtml;

    newEquipamentoEdit.length = 0;
    deletedEquipamentoIds.length = 0;
    // Limpa os inputs também
    if (equipamentoModeloEditEl) equipamentoModeloEditEl.value = "";
    if (equipamentoSerialEditEl) equipamentoSerialEditEl.value = "";
    if (equipamentoMacEditEl) equipamentoMacEditEl.value = ""; // Clear MAC field
    if (equipamentoIotEditEl) equipamentoIotEditEl.checked = false; // Clear IoT checkbox
    if (equipamentoDescricaoEditEl) equipamentoDescricaoEditEl.value = "";
    if (equipamentoVersaoEditEl) equipamentoVersaoEditEl.value = ""; // Clear Versao field

    // Limpeza Links
    const linkContainer = document.getElementById("log-link-edit");
    if (linkContainer) linkContainer.innerHTML = linkEditHeaderHtml;
    // No need to clear newLinksEdit/deletedLinkIds here, they are handled by saveEdit
    // Clear link form fields
    clearLinkForm('edit');

    if (document.getElementById("editLogInput")) document.getElementById("editLogInput").value = "";
    toggleEditButtons('edit', false); // Ensure buttons are reset
  });
}

// Limpa equipamentos QUANDO FECHA O MODAL DE CRIAÇÃO
if (createModalEl) {
  createModalEl.addEventListener("hide.bs.modal", () => {
    // Lógica de limpeza para equipamentos
    const container = document.getElementById("log-equipamento-create");
    if (container) container.innerHTML = equipamentoCreateHeaderHtml;

    newEquipamentoCreate.length = 0;
    // Limpa os inputs também
    if (equipamentoModeloCreateEl) equipamentoModeloCreateEl.value = "";
    // Missing clear for other equipment fields
    // if (equipamentoSerialCreateEl) equipamentoSerialCreateEl.value = "";
    if (equipamentoSerialCreateEl) equipamentoSerialCreateEl.value = "";
    if (equipamentoDescricaoCreateEl) equipamentoDescricaoCreateEl.value = "";

    if (document.getElementById("createLogInput")) document.getElementById("createLogInput").value = "";
  });
}

// -------------------------------------------------
// Funções para RECARREGAR Observações e Equipamentos
// -------------------------------------------------

/**
 * Recarrega e renderiza as observações de um atendimento.
 * @param {Array} observacoesData - O array de observações já buscado do backend.
 */
function reloadObservacoes(observacoesData) {
  // Limpa o container, mantendo o cabeçalho
  if (logContainerObservacao) {
    logContainerObservacao.innerHTML = observacaoHeaderHtml;
  }

  // Array temporário para os itens que vêm do banco de dados
  const existingObservations = [];

  if (Array.isArray(observacoesData)) {
    observacoesData.forEach((obs) => {
      // Cria um objeto com a estrutura que a função de renderização espera
      const obsObj = {
        id_observacao: obs.id,
        data_observacao: obs.timestamp,
        observacao_prodesp: obs.texto,
      };
      existingObservations.push(obsObj);

      // Renderiza o card.
      // A lógica do botão de apagar irá funcionar no array `existingObservations`
      // e adicionar o ID ao array global `deletedObservacaoIds`.
      renderObservacaoCard(
        obsObj,
        logContainerObservacao,
        existingObservations,
        deletedObservacaoIds
      );
    });
  }
}

/**
 * Recarrega e renderiza os equipamentos de uma Unidade no modal.
 * @param {Array} equipamentosData - O array de equipamentos já buscado do backend.
 * @param {string} context - 'edit' ou 'create' (para determinar qual container usar).
 */
function reloadEquipamentos(equipamentosData, context = 'edit') {
  const logContainer = document.getElementById(`log-equipamento-${context}`);
  if (logContainer) {
    logContainer.innerHTML = context === 'edit' ? equipamentoEditHeaderHtml : equipamentoCreateHeaderHtml;
  }

  const targetArray = context === 'edit' ? existingEquipments : existingEquipmentsCreate;
  targetArray.length = 0;

  if (Array.isArray(equipamentosData)) {
    equipamentosData.forEach((eq) => {
      // Cria um objeto com a estrutura que a função de renderização espera
      const eqObj = {
        id_equipamento: eq.id,
        modelo: eq.modelo,
        serial: eq.serial.trim().toUpperCase(),
        versao: eq.versao, // Ensure version is passed
        descricao: eq.descricao,
      };
      targetArray.push(eqObj);

      // Renderiza o card
      renderEquipamentoCard(
        eqObj,
        logContainer,
        targetArray,
        context === 'edit' ? deletedEquipamentoIds : null, // Only pass deleted array for edit context
        context
      );
    });
  }
}

function reloadLinks(linksData, context = 'edit') {
  const logContainer = document.getElementById(`log-link-${context}`);
  if (logContainer) {
    logContainer.innerHTML = context === 'edit' ? linkEditHeaderHtml : linkCreateHeaderHtml;
  }

  if (context === 'edit') {
    existingLinks.length = 0;
  } else {
    existingLinksCreate.length = 0; // Clear for create context
  }

  if (Array.isArray(linksData)) {
    linksData.forEach((lnk) => {
      const lnkObj = {
        id_link: lnk.id,
        id_vgr: lnk.id_vgr_links,
        designador: lnk.designador_links,
        tipo: lnk.tipo_links,
        operadora: lnk.operadora_links,
        vlan: lnk.vlan_links,
        ip_wan: lnk.ip_wan_links,
        ip_gateway: lnk.ip_gateway_links,
        ip_mascara: lnk.ip_mascara_links,
        velocidade: lnk.velocidade_links,
        pppoe_user: lnk.pppoe_user_links,
        pppoe_pass: lnk.pppoe_pass_links,
      };
      
      if (context === 'edit') {
        existingLinks.push(lnkObj);
      } else {
        existingLinksCreate.push(lnkObj); // Add to create context array
      }

      renderLinkCard(lnkObj, logContainer, context === 'edit' ? existingLinks : existingLinksCreate, context === 'edit' ? deletedLinkIds : null, context);
    });
  }
}

// ------------------------------
// RENDER MARCOS EXIBIÇÃO
// ------------------------------
function renderMarcos(marcos) {
  // 🛑 Caso não haja dados, exibe mensagem padrão
  if (!marcos || !marcos.length) {
    return `<div class="text-center text-muted p-3"><em>— Nenhum marco registrado —</em></div>`;
  }

  // ⏱️ Metas definidas por etapa (Exemplo adaptado para PRODESP)
  const metas = {
    "Triagem": { horaIdeal: 8, duracaoIdeal: 1 * 3600 },
    "Em Configuração Remota": { horaIdeal: 9, duracaoIdeal: 2 * 3600 },
    "Em Configuração do MPLS": { horaIdeal: 11, duracaoIdeal: 1 * 3600 },
    "Em Caderno de Teste": { horaIdeal: 12, duracaoIdeal: 1 * 3600 },
    "Concluído": { horaIdeal: 13, duracaoIdeal: 0 },
  };

  // 📅 Formata datas
  const formatar = (str) => {
    if (!str) return "—";
    const d = new Date(str);
    return `${d.toLocaleDateString("pt-BR")} às ${d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  };

  // ⏳ Converte segundos em "HH:mm:ss"
  const formatarDuracao = (segundos) => {
    if (segundos == null || isNaN(segundos)) return "—";
    const h = Math.floor(segundos / 3600);
    const m = Math.floor((segundos % 3600) / 60);
    const s = Math.floor(segundos % 60);
    return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // 🎨 Define a cor da linha (Lógica baseada em intervalos de 15 minutos)
  const getClasse = (marco, duracao) => {
    if (!duracao || marco === "Concluído") return "";

    const minutos = duracao / 60;

    if (minutos >= 30) return "vermelho";
    if (minutos >= 15) return "amarelo";
    return "azul";
  };

  // 📋 Gera texto legível da meta
  const formatarMeta = (marco, meta) => {
    // Mantém o nome do marco simples, já que a meta de tempo agora é fixa pela regra de cores
    return marco;
  };

  // 📊 Legenda
  const legendaHTML = `
    <div class="mb-3 small">
      <strong>Legenda:</strong>
      <div class="mt-2"><span class="badge bg-info text-dark">Azul</span> — Até 15 minutos</div>
      <div class="mt-2"><span class="badge bg-warning text-dark">Amarelo</span> — Entre 15 e 30 minutos</div>
      <div class="mt-2"><span class="badge bg-danger">Vermelho</span> — Acima de 30 minutos</div>
    </div>
  `;

  // 📦 Gera a tabela
  return `
    <h6 class="text-uppercase text-secondary mb-3 mt-3">⏳ Marcos da Atividade</h6>
    ${legendaHTML}
    <div class="table-responsive mt-4">
      <table class="table table-bordered table-sm">
        <thead>
          <tr>
            <th>Marco</th>
            <th>Início</th>
            <th>Fim</th>
            <th>Duração</th>
          </tr>
        </thead>
        <tbody>
          ${marcos.map((m) => {
    const classe = getClasse(m.marco, m.duracao);
    let cor = "";
    if (classe === "vermelho") cor = "table-danger";
    else if (classe === "amarelo") cor = "table-warning";
    else if (classe === "azul") cor = "table-info";
    const meta = metas[m.marco];

    return `
                <tr class="${cor}">
                  <td>${formatarMeta(m.marco, meta)}</td>
                  <td>${formatar(m.inicio)}</td>
                  <td>${formatar(m.fim)}</td>
                  <td>${formatarDuracao(m.duracao)}</td>
                </tr>
              `;
  }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

// ------------------------------
// RENDER HISTÓRICO
// ------------------------------
function renderHistorico(historicoData, isAdmin) {
  if (!historicoData || historicoData.length === 0) {
    return '<div class="text-muted ms-2 mt-2">Nenhum histórico encontrado.</div>';
  }

  const formatarData = (dataStr) => {
    if (!dataStr) return "—";
    try {
      const dataObj = new Date(dataStr);
      if (!isNaN(dataObj.getTime())) {
        return dataObj.toLocaleString("pt-BR");
      }
    } catch (e) { }
    return dataStr;
  };

  if (isAdmin) {
    const tableRows = historicoData.map((log) => {
      return `
        <tr>
          <td>${formatarData(log.data_alteracao_historico)}</td>
          <td>${log.usuario_re_historico || ''} – ${log.usuario_nome_historico || "—"}</td>
          <td>${log.campo_alterado_historico || "—"}</td>
          <td>${log.valor_antigo_historico || "—"}</td>
          <td>${log.valor_novo_historico || "—"}</td>
          <td>${log.operacao_historico || "—"}</td>
        </tr>
      `;
    }).join("");

    return `<div class="table-responsive"><table class="table table-sm table-striped table-hover"><thead><tr><th>Data</th><th>Usuário</th><th>Campo Alterado</th><th>Valor Antigo</th><th>Valor Novo</th><th>Op.</th></tr></thead><tbody>${tableRows}</tbody></table></div>`;
  } else {
    const tableRows = historicoData.map((log) => `
      <tr>
        <td>${formatarData(log.data_alteracao_historico)}</td>
        <td>${log.usuario_re_historico || ''} – ${log.usuario_nome_historico || "—"}</td>
        <td>${log.valor_novo_historico || "—"}</td>
      </tr>
    `).join("");

    return `<div class="table-responsive"><table class="table table-sm table-striped table-hover"><thead><tr><th>Data</th><th>Usuário</th><th>Informação</th></tr></thead><tbody>${tableRows}</tbody></table></div>`;
  }
}

/**
 * Abre o modal de criação de atendimento já preenchendo o ID VGR e disparando o carregamento.
 * @param {string} idVgr - O ID VGR da unidade.
 */
function openCreateWithVgr(idVgr) {
  openCreateModal();
  const el = document.getElementById("createIdVgr");
  if (el) {
    el.value = idVgr;
    // Dispara o evento blur para que a lógica existente de carregamento via ID VGR seja executada
    el.dispatchEvent(new Event('blur'));
  }
}

/**
 * Visualiza os dados da unidade e conectividade (pré-carregamento) quando não há atendimento.
 * @param {string} idVgr - O ID VGR da unidade.
 */
function viewUnitOnly(idVgr) {
  fetch(`/prodesp/unidades/${encodeURIComponent(idVgr)}`)
    .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
    .then(json => {
      if (!json.success) throw new Error(json.message);
      const u = json.unidade;
      
      // Objeto fake para preencher os campos da unidade no modal de visualização
      const d = {
        ...u,
        id_atendimentos: null,
        status_atendimento: "Agendado",
        substatus_atendimento: "",
        analista_atuante: "",
        analista_configuracao: "",
        analista_mpls_atendimentos: "",
        analista_caderno_teste: "",
        contratada: "",
        field_responsavel: "",
        contato_field: "",
        logs_atendimento: "",
        data_atendimento: null,
        observacoes: [],
        equipamentos: u.equipamentos || [],
        links: u.links || [],
        ip_lan_01: u.ip_lan_01 || "",
        ip_lan_02: u.ip_lan_02 || ""
      };

      fillModalFields(d, 'view');
      
      // Renderiza as seções de listas como vazias ou com dados da unidade
      const obsContainer = document.getElementById("log-observacao-view");
      obsContainer.innerHTML = '<div class="titles-incident"><span>DATA</span><span>OBSERVAÇÕES</span></div><div class="text-muted p-2">Nenhuma observação registrada.</div>';

      const eqContainer = document.getElementById("log-equipamento-view");
      eqContainer.innerHTML = '<div class="titles-incident"><span>MODELO</span><span>SERIAL</span><span>VERSÃO</span><span>DESCRIÇÃO</span></div>';
      if (d.equipamentos.length > 0) {
        d.equipamentos.forEach(eq => {
          const row = document.createElement("div");
          row.classList.add("card-incident");
          row.innerHTML = `
            <div class="fields">
              <div class="incident-data">${eq.modelo || '-'}</div>
              <div class="incident-data">${eq.serial || '-'}</div>
              <div class="incident-data">${eq.versao || '-'}</div>
              <div class="incident-data">${eq.descricao || '-'}</div>
            </div>`;
          eqContainer.appendChild(row);
        });
      } else {
        eqContainer.innerHTML += '<div class="text-muted p-2">Nenhum equipamento cadastrado.</div>';
      }

      const lnkContainer = document.getElementById("log-link-view");
      lnkContainer.innerHTML = '<div class="titles-incident"><span>ID LINK</span><span>TIPO</span><span>DESIGNADOR</span><span>OPERADORA</span><span>VLAN</span><span>VELOCIDADE</span><span>IP WAN</span><span>GATEWAY</span><span>MÁSCARA</span><span>PPPOE USER</span><span>PPPOE PASS</span></div>';
      if (d.links.length > 0) {
        d.links.forEach(lnk => {
          const row = document.createElement("div");
          row.classList.add("card-incident");
          row.innerHTML = `
            <div class="fields">
              <div class="incident-data">${lnk.id_vgr_links || '-'}</div>
              <div class="incident-data">${lnk.tipo_links || '-'}</div>
              <div class="incident-data">${lnk.designador_links || '-'}</div>
              <div class="incident-data">${lnk.operadora_links || '-'}</div>
              <div class="incident-data">${lnk.vlan_links || '-'}</div>
              <div class="incident-data">${lnk.velocidade_links || '-'}</div>
              <div class="incident-data">${lnk.ip_wan_links || '-'}</div>
              <div class="incident-data">${lnk.ip_gateway_links || '-'}</div>
              <div class="incident-data">${lnk.ip_mascara_links || '-'}</div>
              <div class="incident-data">${lnk.pppoe_user_links || '-'}</div>
              <div class="incident-data">${lnk.pppoe_pass_links || '-'}</div>
            </div>`;
          lnkContainer.appendChild(row);
        });
      } else {
        lnkContainer.innerHTML += '<div class="text-muted p-2">Nenhum link cadastrado.</div>';
      }

      document.getElementById("log-marcos-view").innerHTML = '<div class="text-center text-muted p-3"><em>— Atendimento não iniciado —</em></div>';
      document.getElementById("log-historico-view").innerHTML = '<div class="text-muted ms-2 mt-2">Nenhum histórico encontrado para esta unidade.</div>';

      bootstrap.Modal.getOrCreateInstance(document.getElementById("viewModal")).show();
    })
    .catch(err => {
      console.error("Erro em viewUnitOnly:", err);
      showToast("Não foi possível carregar os dados da unidade.", "danger");
    });
}

// ------------------------------
// REDEFINE window para onclick
// ------------------------------
window.viewDetails = viewDetails;
window.editDetails = editDetails;
window.saveEdit = saveEdit;
window.openCreateWithVgr = openCreateWithVgr;
window.viewUnitOnly = viewUnitOnly;
