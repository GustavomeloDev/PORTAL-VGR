document.addEventListener('DOMContentLoaded', function() {
    // Card click handler
    const cards = document.querySelectorAll('.k-card[data-details-url]');
    
    cards.forEach(card => {
        card.addEventListener('click', function(e) {
            // Não navegar se o usuário estiver selecionando texto
            if (window.getSelection().toString().length > 0) return;
            
            // Navegar para a URL detalhada
            const url = this.dataset.detailsUrl;
            if (url) {
                window.location.href = url;
            }
        });
    });

    // Curation buttons handler
    const curationBtns = document.querySelectorAll('.curation-btn');
    curationBtns.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const id = this.dataset.lessonId;
            const action = this.dataset.action;
            
            if (!confirm('Confirmar ' + (action === 'approve' ? 'aprovação' : 'rejeição') + ' desta lição?')) return;

            fetch(`/aprendizado/curadoria/${id}/${action}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => {
                if (response.ok) {
                    // Remove row from table
                    const row = document.getElementById(`row-${id}`);
                    if (row) {
                        row.style.opacity = '0';
                        setTimeout(() => row.remove(), 300);
                    }
                    if (window.toastr) {
                        toastr.success(`Lição ${action === 'approve' ? 'aprovada' : 'rejeitada'} com sucesso!`);
                    } else {
                        alert(`Lição ${action === 'approve' ? 'aprovada' : 'rejeitada'} com sucesso!`);
                    }
                } else {
                    if (window.toastr) {
                        toastr.error('Erro ao processar requisição.');
                    } else {
                        alert('Erro ao processar requisição.');
                    }
                }
            })
            .catch(error => {
                console.error('Error:', error);
                if (window.toastr) {
                    toastr.error('Erro de conexão.');
                } else {
                    alert('Erro de conexão.');
                }
            });
        });
    });
});
