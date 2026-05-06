from flask import Blueprint, request, jsonify
import database

plates_bp = Blueprint('plates', __name__)


@plates_bp.route('/api/plates/', methods=['GET'])
def get_plates():
    """Gibt alle Kennzeichen aus der Whitelist zurück.
    Mit ?nur_aktive=true werden nur aktivierte Einträge zurückgegeben."""
    nur_aktive = request.args.get('nur_aktive', 'false').lower() == 'true'
    plates = database.get_all_plates(nur_aktive=nur_aktive)
    return jsonify([{
        'id':           p['id'],
        'kennzeichen':  p['plate_number'],
        'beschreibung': p['beschreibung'],
        'aktiv':        bool(p['aktiv']),
        'created_at':   p['created_at'],
    } for p in plates])


@plates_bp.route('/api/plates/', methods=['POST'])
def add_plate():
    """Fügt ein neues Kennzeichen zur Whitelist hinzu."""
    data = request.get_json()
    kennzeichen  = (data.get('kennzeichen') or '').upper().strip()
    beschreibung = data.get('beschreibung')
    if not kennzeichen:
        return jsonify({'error': 'Kennzeichen fehlt'}), 400
    ok = database.add_plate(kennzeichen, beschreibung)
    if not ok:
        return jsonify({'error': 'Bereits vorhanden'}), 409
    return jsonify({'status': 'ok'}), 201


@plates_bp.route('/api/plates/<int:plate_id>', methods=['PATCH'])
def toggle_plate(plate_id):
    """Aktiviert oder deaktiviert ein Kennzeichen (ohne es zu löschen)."""
    data = request.get_json()
    database.set_plate_active(plate_id, data.get('aktiv', True))
    return jsonify({'status': 'ok'})


@plates_bp.route('/api/plates/<int:plate_id>', methods=['DELETE'])
def delete_plate(plate_id):
    """Löscht ein Kennzeichen aus der Whitelist."""
    database.remove_plate(plate_id)
    return jsonify({'status': 'ok'})


@plates_bp.route('/api/plates/log/history')
def log_history():
    """Gibt die letzten Zugriffsversuche zurück (erlaubt und abgelehnt)."""
    limit = int(request.args.get('limit', 100))
    logs = database.get_recent_logs(limit)
    return jsonify([{
        'kennzeichen': l['plate_number'],
        'erlaubt':     bool(l['access_granted']),
        'erkannt':     l['plate_number'] is not None,
        'konfidenz':   l['konfidenz'],
        'zeitstempel': l['timestamp'],
    } for l in logs])
