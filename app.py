import os
import subprocess
import threading
import time
import json
import requests
import shutil
from datetime import datetime
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session, flash
from flask_cors import CORS
from werkzeug.utils import secure_filename
import jwt
from functools import wraps

# Chave secreta JWT compartilhada com o Node.js
JWT_SECRET = "OCPKRhjDcmz0AjjVWqNO1/60H1z7bfmJDmrpMgIUWlg="

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Mude para uma chave segura em produção

# Decorator para proteger rotas com JWT

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.cookies.get('token')
        if not token:
            return redirect('http://140.238.180.148:3000/')  # Redireciona para o login do Node.js
        try:
            jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except Exception:
            return redirect('http://140.238.180.148:3000/')
        return f(*args, **kwargs)
    return decorated_function

# Configurações
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024  # 10 GB
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Desativa o cache para desenvolvimento

# Verificar se o arquivo tem extensão
def allowed_file(filename):
    return '.' in filename

# Adicionar filtro datetime
@app.template_filter('datetime')
def format_datetime(value, format="%d/%m/%Y %H:%M"):
    if value is None:
        return ""
    return datetime.fromtimestamp(value).strftime(format)

# Rota de logout
@app.route('/logout')
def logout():
    resp = redirect('http://140.238.180.148:3000/')
    resp.set_cookie('token', '', expires=0, path='/', samesite='Lax')
    return resp

# Rota principal - Listagem de arquivos
# GARANTA QUE ESTA ROTA ESTÁ PROTEGIDA POR LOGIN
@app.route('/')
@app.route('/<path:folder_path>')
@login_required
def index(folder_path=''):
    base_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_path)
    
    if not os.path.exists(base_path):
        return redirect(url_for('index'))
    
    # Breadcrumbs
    breadcrumbs = []
    parts = folder_path.split('/') if folder_path else []
    for i in range(len(parts)):
        breadcrumbs.append({
            'name': parts[i],
            'path': '/'.join(parts[:i+1])
        })
    
    # Listar arquivos e pastas
    items = os.listdir(base_path)
    files = []
    folders = []
    
    for item in items:
        full_path = os.path.join(base_path, item)
        if os.path.isfile(full_path):
            files.append({
                'name': item,
                'path': folder_path,
                'size': f"{os.path.getsize(full_path) / 1024:.2f} KB",
                'modified': os.path.getmtime(full_path),
                'is_root': not bool(folder_path)
            })
        else:
            try:
                # Contagem segura de arquivos
                sub_items = os.listdir(full_path)
                file_count = len([f for f in sub_items if os.path.isfile(os.path.join(full_path, f))])
            except Exception:
                file_count = 0  # Fallback seguro
                
            folders.append({
                'name': item,
                'path': os.path.join(folder_path, item) if folder_path else item,
                'file_count': file_count
            })
    
    # Listar todas as pastas para o menu de movimentação
    all_folders = []
    for root, dirs, _ in os.walk(app.config['UPLOAD_FOLDER']):
        for dir_name in dirs:
            rel_path = os.path.relpath(os.path.join(root, dir_name), app.config['UPLOAD_FOLDER'])
            all_folders.append({
                'name': dir_name,
                'path': rel_path if rel_path != '.' else ''
            })
    
    sort_column = request.args.get('sort', 'name')
    sort_dir = request.args.get('dir', 'asc')
    reverse = (sort_dir == 'desc')

    if sort_column == 'name':
        files.sort(key=lambda x: x['name'].lower(), reverse=reverse)
    elif sort_column == 'size':
        files.sort(key=lambda x: x['size'], reverse=reverse)
    elif sort_column == 'date':
        files.sort(key=lambda x: x['modified'], reverse=reverse)
    
    return render_template('file_list.html', 
                         files=files, 
                         folders=folders,
                         all_folders=all_folders,
                         breadcrumbs=breadcrumbs,
                         current_path=folder_path,
                         sort_column=sort_column,
                         sort_dir=sort_dir)

# Rota de upload modificada

# Rota para upload em partes (chunked upload)
from flask import Response

@app.route('/merge_chunks', methods=['POST'])
def merge_chunks():
    filename = request.form.get('filename')
    total_chunks = request.form.get('total_chunks')
    current_path = request.form.get('current_path', '')
    app.logger.info(f"[MERGE_CHUNKS] Solicitado merge: filename={filename}, total_chunks={total_chunks}, current_path={current_path}")
    try:
        total_chunks = int(total_chunks)
    except Exception:
        return Response('total_chunks inválido', status=400)
    if not filename or not total_chunks:
        return Response('Missing filename ou total_chunks', status=400)
    dest_folder = os.path.join(app.config['UPLOAD_FOLDER'], current_path)
    final_path = os.path.join(dest_folder, secure_filename(filename))
    lock_path = final_path + '.lock'
    # Checa se todos os chunks existem
    for i in range(1, total_chunks+1):
        part_path = os.path.join(dest_folder, f"{filename}.part{i:04d}")
        if not os.path.exists(part_path):
            app.logger.warning(f"[MERGE_CHUNKS] Chunk faltando: {part_path}")
            return Response(f'Chunk faltando: {part_path}', status=400)
    try:
        if os.path.exists(lock_path):
            app.logger.warning(f"[MERGE_CHUNKS] Outro processo está montando: {lock_path}")
            return Response('Já existe montagem em andamento', status=409)
        with open(lock_path, 'w') as lockfile:
            lockfile.write('lock')
        app.logger.info(f"[MERGE_CHUNKS] Iniciando montagem do arquivo final: {final_path}")
        with open(final_path, 'wb') as f_out:
            for i in range(1, total_chunks+1):
                part_path = os.path.join(dest_folder, f"{filename}.part{i:04d}")
                with open(part_path, 'rb') as f_in:
                    shutil.copyfileobj(f_in, f_out)
                os.remove(part_path)
        app.logger.info(f"[MERGE_CHUNKS] Arquivo montado com sucesso: {final_path}")
        os.remove(lock_path)
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"[MERGE_CHUNKS] Erro ao montar arquivo final: {e}")
        if os.path.exists(lock_path):
            os.remove(lock_path)
        return jsonify({'success': False, 'message': f'Erro ao montar arquivo final: {str(e)}'}), 500

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    # --- LOG DE DEBUG INÍCIO ---
    filename = request.form.get('filename') or request.form.get('resumableFilename')
    chunk_index = request.form.get('chunk_index') or request.form.get('resumableChunkNumber')
    total_chunks = request.form.get('total_chunks') or request.form.get('resumableTotalChunks')
    current_path = request.form.get('current_path', '')
    app.logger.info(f"[UPLOAD_CHUNK] Recebido chunk: filename={filename}, chunk_index={chunk_index}, total_chunks={total_chunks}, current_path={current_path}")

    # Conversão de tipos
    try:
        chunk_index = int(chunk_index)
    except Exception:
        chunk_index = 1
    try:
        total_chunks = int(total_chunks)
    except Exception:
        total_chunks = 1
    if not filename or 'file' not in request.files:
        app.logger.error(f"[UPLOAD_CHUNK] Erro: Missing filename or file. filename={filename}, chunk_index={chunk_index}, total_chunks={total_chunks}")
        return Response('Missing filename or file', status=400)

    dest_folder = os.path.join(app.config['UPLOAD_FOLDER'], current_path)
    os.makedirs(dest_folder, exist_ok=True)

    # Nome do chunk temporário
    chunk_name = f"{filename}.part{chunk_index:04d}"
    chunk_path = os.path.join(dest_folder, chunk_name)
    try:
        app.logger.info(f"[UPLOAD_CHUNK] Salvando chunk {chunk_index}/{total_chunks}: {chunk_path}")
        request.files['file'].save(chunk_path)
        app.logger.info(f"[UPLOAD_CHUNK] Chunk salvo com sucesso: {chunk_path}")
    except Exception as e:
        app.logger.error(f"[UPLOAD_CHUNK] Erro ao salvar chunk {chunk_index}: {e}")
        return Response(f'Erro ao salvar chunk {chunk_index}: {e}', status=500)

    # LOG EXTRA: Estado dos arquivos após salvar chunk
    import glob
    chunk_files = glob.glob(os.path.join(dest_folder, filename + '.part*'))
    app.logger.info(f"[UPLOAD_CHUNK] Arquivos de chunk existentes: {chunk_files}")
    app.logger.info(f"[UPLOAD_CHUNK] Arquivo final existe? {os.path.exists(os.path.join(dest_folder, secure_filename(filename)))}")

    # Após salvar o chunk, apenas loga e retorna sucesso. O merge será feito via /merge_chunks
    return Response('OK', status=200)



@app.route('/upload', methods=['POST'])
def upload_file():
    print('DEBUG UPLOAD FORM:', dict(request.form))
    # O valor de folder será mostrado logo abaixo
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Nenhum arquivo enviado.'}), 400
    files = request.files.getlist('file')
    # Suporte tanto a 'current_path' quanto a 'folder' como destino
    folder = request.form.get('current_path') or request.form.get('folder') or ''
    dest_dir = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    print('DEBUG DESTINO:', dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    saved_count = 0
    for file in files:
        if file.filename == '':
            continue
        filename = secure_filename(file.filename)
        file.save(os.path.join(dest_dir, filename))
        saved_count += 1
    if saved_count == 0:
        return jsonify({'success': False, 'message': 'Nenhum arquivo válido enviado.'}), 400
    return jsonify({'success': True, 'message': f'{saved_count} arquivo(s) enviado(s) com sucesso.'})

# Nova rota para mover arquivos
@app.route('/move_files', methods=['POST'])
def move_files():
    try:
        target_folder = request.form.get('target_folder', '')
        selected_files = request.form.getlist('selected_files')
        current_path = request.form.get('current_path', '')
        
        for filename in selected_files:
            src = os.path.join(app.config['UPLOAD_FOLDER'], current_path, filename)
            dst = os.path.join(app.config['UPLOAD_FOLDER'], target_folder, filename)
            os.rename(src, dst)
            
        flash('Arquivos movidos com sucesso', 'success')
    except Exception as e:
        flash(f'Erro ao mover arquivos: {str(e)}', 'error')
    
    return redirect(request.referrer or url_for('index'))

# Rota de download com logs
@app.route('/download/<path:filepath>')
def download(filepath):
    try:
        if filepath.startswith('root/'):
            filepath = filepath[5:]
        directory = os.path.join(app.config['UPLOAD_FOLDER'], os.path.dirname(filepath))
        return send_from_directory(
            directory=directory,
            path=os.path.basename(filepath),
            as_attachment=True
        )
    except Exception as e:
        flash(f'Erro ao baixar arquivo: {str(e)}')
        return redirect(url_for('index'))

# Rota para excluir arquivo (compatível com frontend JS)
@app.route('/delete_file', methods=['POST'])
def delete_file_post():
    old_name = request.form.get('old_name')
    current_path = request.form.get('current_path', '')
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_path, old_name)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            flash('Arquivo excluído com sucesso', 'success')
        else:
            flash('Arquivo não encontrado', 'error')
    except Exception as e:
        flash(f'Erro ao excluir arquivo: {str(e)}', 'error')
    return redirect(request.referrer or url_for('index'))

# Rota para excluir arquivo (legacy, aceita via URL)
@app.route('/delete/<path:filename>', methods=['POST'])
def delete_file(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            flash('Arquivo excluído com sucesso', 'success')
        else:
            flash('Arquivo não encontrado', 'error')
    except Exception as e:
        flash(f'Erro ao excluir arquivo: {str(e)}', 'error')
    return redirect(request.referrer or url_for('index'))

# Rota para gerenciamento de pastas
@app.route('/folder_action', methods=['POST'])
def folder_action():
    action = request.form.get('action')
    folder_name = request.form.get('folder_name')
    new_name = request.form.get('new_name', '')
    current_path = request.form.get('current_path', '')
    # Sanitização
    folder_name = folder_name.strip() if folder_name else folder_name
    current_path = current_path.strip() if current_path else current_path
    new_name = new_name.strip() if new_name else new_name
    
    try:
        # LOG para depuração
        print('--- FOLDER_ACTION DEBUG ---')
        print('action:', action)
        print('current_path:', current_path)
        print('folder_name:', folder_name)
        print('new_name:', new_name)
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], current_path, folder_name)
        new_folder_path = os.path.join(app.config['UPLOAD_FOLDER'], current_path, new_name)
        print('folder_path:', folder_path)
        print('new_folder_path:', new_folder_path)
        print('JOINED PATH:', os.path.join(app.config['UPLOAD_FOLDER'], current_path, folder_name))
        print('---------------------------')

        if action == 'create' and folder_name:
            os.makedirs(folder_path, exist_ok=True)
            flash(f'Pasta "{folder_name}" criada!')
        
        elif action == 'rename' and folder_name and new_name:
            os.rename(folder_path, new_folder_path)
            flash(f'Pasta renomeada para "{new_name}"!')
        
        elif action == 'delete' and folder_name:
            shutil.rmtree(folder_path)
            flash(f'Pasta "{folder_name}" excluída!')
            
    except Exception as e:
        flash(f'Erro: {str(e)}')
    
    return redirect(url_for('index', folder_path=current_path))

# Rota para renomear arquivos
@app.route('/rename_file', methods=['POST'])
def rename_file():
    current_path = request.form.get('current_path', '')
    old_name = request.form.get('old_name')
    new_name = request.form.get('new_name')

    # Permitir espaços e acentos em arquivos e pastas; só bloquear nomes inválidos
    def is_file(name):
        return '.' in name and not name.startswith('.')

    if '/' in new_name or '\\' in new_name or not new_name.strip():
        flash('Nome inválido!')
        return redirect(url_for('index', folder_path=current_path))
    new_name = new_name.strip()

    if not old_name or not new_name:
        flash('Nomes inválidos')
        return redirect(url_for('index', folder_path=current_path))

    if old_name == new_name:
        return redirect(url_for('index', folder_path=current_path))

    old_path = os.path.join(app.config['UPLOAD_FOLDER'], current_path, old_name)
    new_path = os.path.join(app.config['UPLOAD_FOLDER'], current_path, new_name)

    if os.path.exists(new_path):
        flash('Já existe um arquivo ou pasta com esse nome!')
        return redirect(url_for('index', folder_path=current_path))

    try:
        os.rename(old_path, new_path)
        flash('Renomeado com sucesso!')
    except Exception as e:
        flash(f'Erro ao renomear: {str(e)}')

    return redirect(url_for('index', folder_path=current_path))

# --- ROTA PARA COMANDOS DO PLEX MEDIA SERVER ---
@app.route('/plex_command', methods=['POST'])
def plex_command():
    data = request.get_json()
    cmd = data.get('cmd')
    allowed_cmds = {
        'start': ['systemctl', 'start', 'plexmediaserver'],
        'stop': ['systemctl', 'stop', 'plexmediaserver'],
        'restart': ['systemctl', 'restart', 'plexmediaserver'],
        'status': ['systemctl', 'status', 'plexmediaserver'],
        'update': ['systemctl', 'reload', 'plexmediaserver'],
        'logs': ['journalctl', '-u', 'plexmediaserver', '-n', '30', '--no-pager'],
        'info': ['ps', 'aux'],
        'enable': ['systemctl', 'enable', 'plexmediaserver'],
        'disable': ['systemctl', 'disable', 'plexmediaserver'],
        'version': ['/usr/lib/plexmediaserver/Plex Media Server', '--version'],
    }
    if cmd not in allowed_cmds:
        return jsonify({'success': False, 'message': 'Comando não permitido.'}), 400
    try:
        # Para comandos que precisam de shell (como version), use shell=True
        shell_needed = cmd == 'version'
        result = subprocess.run(
            ' '.join(allowed_cmds[cmd]) if shell_needed else allowed_cmds[cmd],
            capture_output=True, text=True, shell=shell_needed
        )
        output = result.stdout.strip() or result.stderr.strip() or 'Comando executado.'
        status = result.returncode == 0
        return jsonify({'success': status, 'message': output})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao executar comando: {str(e)}'}), 500

# Configuração para produção
#if __name__ == "__main__":
#    app.run(host="0.0.0.0", port=5000)
