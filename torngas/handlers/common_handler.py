#-*-coding=utf-8-*-
import base64
import hmac
import hashlib
import time
import threading
import re
from urllib import unquote
from tornado.escape import utf8
import tornado
from torngas import exception
from torngas.mixin.handler_mixin import UncaughtExceptionMixin, FlashMessageMixIn
from torngas.helpers import settings_helper, logger_helper
from torngas.dispatch import signals


class CommonHandler(tornado.web.RequestHandler):
    def __init__(self, application, request, **kwargs):
        super(CommonHandler, self).__init__(application, request, **kwargs)
        self._is_threaded = False
        self._is_torngas_finished = False


    def initialize(self, **kwargs):
        self.appname = kwargs.get('app_name', None)


    def prepare(self):
        signals.handler_started.send(sender=self.__class__)
        self.application.middleware_manager.run_request_hooks(self)

    def reverse_url(self, name, *args):
        return super(CommonHandler, self).reverse_url(self.appname + '-' + name, *args)

    def create_post_token(self):
        """返回一个当前时间戳的16进制哈希码，用来做post 请求的验证token"""
        timestamp = utf8(str(int(time.time())))
        value = base64.b64encode(utf8(timestamp))
        hashtxt = hmac.new(utf8(value), digestmod=hashlib.sha1)
        return utf8(hashtxt.hexdigest())


    @property
    def logger(self):
        return logger_helper.logger.getlogger

    @property
    def cache(self):
        return self.application.cache

    def finish(self, chunk=None):

        signals.handler_finished.send(sender=self.__class__)
        self._is_torngas_finished = True
        self.application.middleware_manager.run_response_hooks(self)
        if self._is_threaded:
            self._chunk = chunk
            tornado.ioloop.IOLoop.instance().add_callback(self.threaded_finish_callback)
            return

        super(CommonHandler, self).finish(chunk)


    def threaded_finish_callback(self):
        """
        如果使用多线程回调装饰器，此方法将起作用
        :return:
        """
        if self.application.settings.get('debug', False):
            print "In the finish callback thread is ", str(threading.currentThread())
        super(CommonHandler, self).finish(self._chunk)
        self._chunk = None

    def get_arguments_dict(self):
        params = {}
        for key in self.request.arguments:
            values = self.get_arguments(key)
            k = unquote(key)
            if len(values) == 1:
                params[k] = values[0]
            else:
                params[k] = values

        return params

    def get_argument(self, name, default=[], strip=True):
        value = super(CommonHandler, self).get_argument(name, default, strip)
        if value == default:
            return value
        return unquote(value)


    def get_user_locale(self):

        if settings_helper.settings.TRANSLATIONS_CONF.use_accept_language:
            return None

        return tornado.locale.get(settings_helper.settings.TRANSLATIONS_CONF.locale_default)

    def _cleanup_param(self, val, strip=True):
        # Get rid of any weird control chars
        value = re.sub(r"[\x00-\x08\x0e-\x1f]", " ", val)
        value = tornado.web._unicode(value)
        if strip: value = value.strip()
        return unquote(value)

    def write(self, chunk, status=None):
        if status:
            self.set_status(status)

        super(CommonHandler, self).write(chunk)


class WebHandler(UncaughtExceptionMixin, CommonHandler, FlashMessageMixIn):
    def get_template_path(self):
        templdir_settings = settings_helper.settings.APPS_TEMPLATES_DIR
        if not templdir_settings:
            raise exception.ConfigError('config {0} section no exist!'.format(templdir_settings))
        if len(templdir_settings):
            apptmpl_dir = templdir_settings.get(self.appname, None)
            print apptmpl_dir
            return ''.join([self.application.project_path, apptmpl_dir, '/']) if apptmpl_dir else None
        else:
            return None


    def create_template_loader(self, template_path):

        loader = self.application.tmpl
        if loader is None:
            return super(CommonHandler, self).create_template_loader(template_path)
        else:
            app_name = self.appname
            return loader(template_path, app_name=app_name)


class ErrorHandler(CommonHandler, UncaughtExceptionMixin):
    """raise 404 error if url is not found.
    fixed tornado.web.RequestHandler HTTPError bug.
    """

    def prepare(self):
        super(ErrorHandler, self).prepare()
        self.set_status(404)
        raise tornado.web.HTTPError(404)


tornado.web.ErrorHandler = ErrorHandler