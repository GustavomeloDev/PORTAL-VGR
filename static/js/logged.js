export const LOGGED = {
    LOGGED_IN_USER_ADMIN: "{{ current_user.admin_user | default(0) }}",
    LOGGED_IN_USER_NAME: "{{ current_user.nome_user | default('') }}",
    LOGGED_IN_USER_DEPARTAMENTOS: {{ current_user.departamentos_todos() | list | tojson }}
}

