"""Jenkins management routes."""
import sys
from . import router
from .logging import get_logger
from core import jenkins

logger = get_logger('jenkins', 'jenkins')

@router.route('GET', '/api/jenkins')
def list_view(ctx):
    server = sys.modules.get('server') or sys.modules['__main__']
    ctx.request.send_json(200, {'ok': True, 'servers': jenkins.list_servers(server.CENTER_PORT)})
    return True

@router.route('POST', '/api/jenkins/save', '/api/jenkins/delete')
def change_view(ctx):
    action = 'delete' if ctx.path.endswith('/delete') else 'save'
    logger.info('jenkins.%s.begin', action)
    try:
        getattr(jenkins, action)(ctx.body)
    except Exception:
        logger.warning('jenkins.%s.failed', action)
        raise
    logger.info('jenkins.%s.end', action)
    ctx.request.send_json(200, {'ok': True})
    return True

@router.route('POST', '/api/jenkins/register')
def register_view(ctx):
    from core.jenkins_signup import register_accounts
    logger.info('jenkins.register.begin')
    try:
        results = register_accounts(ctx.body)
    except Exception:
        logger.warning('jenkins.register.failed')
        raise
    logger.info('jenkins.register.end count=%s', len(results))
    ctx.request.send_json(200, {'ok': True, 'results': results})
    return True

@router.route('POST', '/api/jenkins/permissions/search', '/api/jenkins/permissions/save')
def permissions_view(ctx):
    from core import jenkins_permissions
    if ctx.path.endswith('/search'):
        result = jenkins_permissions.search(ctx.body)
        ctx.request.send_json(200, {'ok': True, 'results': result})
    else:
        result = jenkins_permissions.save(ctx.body)
        ctx.request.send_json(200, {'ok': True, 'result': result})
    return True
