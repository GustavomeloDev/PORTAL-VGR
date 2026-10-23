from flask import Blueprint


def create_blueprint(blueprint_name, file_name, template_folder='templates', static_folder='static'):
    bp = Blueprint(
        blueprint_name, file_name,
        template_folder=template_folder,  # Caminho para templates
        static_folder=static_folder,  # Caminho para arquivos estáticos
        url_prefix='/{}'.format(blueprint_name),
    )
    return bp