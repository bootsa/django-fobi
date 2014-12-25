__title__ = 'fobi.contrib.apps.mezzanine_integration.page_processors'
__author__ = 'Artur Barseghyan <artur.barseghyan@gmail.com>'
__copyright__ = 'Copyright (c) 2014 Artur Barseghyan'
__license__ = 'GPL 2.0/LGPL 2.1'
__all__ = ('FobiFormProcessor', 'process_fobi_form',)

from django.utils.translation import ugettext_lazy as _
from django.template.loader import render_to_string
from django.template import RequestContext
from django.contrib import messages
from django.shortcuts import redirect
from django.conf import settings

from mezzanine.conf import settings
from mezzanine.pages.page_processors import processor_for

from fobi.dynamic import assemble_form_class
from fobi.base import (
    fire_form_callbacks, run_form_handlers,
    submit_plugin_form_data, get_theme
    )
from fobi.constants import (
    CALLBACK_BEFORE_FORM_VALIDATION, CALLBACK_FORM_INVALID,
    CALLBACK_FORM_VALID_BEFORE_SUBMIT_PLUGIN_FORM_DATA, CALLBACK_FORM_VALID,
    CALLBACK_FORM_VALID_AFTER_FORM_HANDLERS
    )
from fobi.contrib.apps.mezzanine_integration.settings import (
    WIDGET_FORM_SENT_GET_PARAM
    )
from fobi.contrib.apps.mezzanine_integration.models import FobiFormPage

class FobiFormProcessor(object):
    def process(self, request, instance, **kwargs):
        """
        This is where most of the form handling happens.

        :param django.http.HttpRequest request:
        :return django.http.HttpResponse | str:
        """
        if WIDGET_FORM_SENT_GET_PARAM in request.GET:
            return self._show_thanks_page(request, instance, **kwargs)
        else:
            return self._process_form(request, instance, **kwargs)

    def _process_form(self, request, instance, **kwargs):
        """
        Handle the form if no "sent" GET argument (see the
        ``WIDGET_FORM_SENT_GET_PARAM`` setting).

        :param django.http.HttpRequest request:
        :return django.http.HttpResponse | str:
        """
        template_name = instance.form_template_name or None

        # Handle public/non-public forms. If form requires user authentication
        # redirect to login form with next parameter set to current request
        # path.
        if not request.user.is_authenticated() and not instance.form_entry.is_public:
            return redirect("{0}?next={1}".format(settings.LOGIN_URL, request.path))

        form_element_entries = instance.form_entry.formelemententry_set.all()[:]
        # This is where the most of the magic happens. Our form is being built
        # dynamically.
        FormClass = assemble_form_class(
            instance.form_entry,
            form_element_entries = form_element_entries
            )

        if 'POST' == request.method:
            form = FormClass(request.POST, request.FILES)

            # Fire pre form validation callbacks
            fire_form_callbacks(
                form_entry = instance.form_entry,
                request = request,
                form = form,
                stage = CALLBACK_BEFORE_FORM_VALIDATION)

            if form.is_valid():
                # Fire form valid callbacks, before handling sufrom
                # django.http import HttpResponseRedirectbmitted plugin
                # form data
                form = fire_form_callbacks(
                    form_entry = instance.form_entry,
                    request = request,
                    form = form,
                    stage = CALLBACK_FORM_VALID_BEFORE_SUBMIT_PLUGIN_FORM_DATA
                    )

                # Fire plugin processors
                form = submit_plugin_form_data(
                    form_entry = instance.form_entry,
                    request = request,
                    form = form
                    )

                # Fire form valid callbacks
                form = fire_form_callbacks(
                    form_entry = instance.form_entry,
                    request = request,
                    form = form,
                    stage = CALLBACK_FORM_VALID
                    )

                # Run all handlers
                run_form_handlers(
                    form_entry = instance.form_entry,
                    request = request,
                    form = form
                    )

                # Fire post handler callbacks
                fire_form_callbacks(
                    form_entry = instance.form_entry,
                    request = request,
                    form = form,
                    stage = CALLBACK_FORM_VALID_AFTER_FORM_HANDLERS
                    )

                messages.info(
                    request,
                    _('Form {0} was submitted successfully.').format(instance.form_entry.name)
                    )

                return redirect(
                    "{0}?{1}={2}".format(request.path, WIDGET_FORM_SENT_GET_PARAM, \
                                         instance.form_entry.slug)
                    )

            else:
                # Fire post form validation callbacks
                fire_form_callbacks(
                    form_entry = instance.form_entry,
                    request = request,
                    form = form,
                    stage = CALLBACK_FORM_INVALID
                    )

        else:
            form = FormClass()

        theme = get_theme(request=request, as_instance=True)
        theme.collect_plugin_media(form_element_entries)

        context = {
            'form': form,
            'form_entry': instance.form_entry,
            'fobi_theme': theme,
            'fobi_form_title': instance.form_title,
            'fobi_hide_form_title': instance.hide_form_title,
            'fobi_form_submit_button_text': instance.form_submit_button_text
        }

        if not template_name:
            template_name = theme.view_embed_form_entry_ajax_template

        self.rendered_output = render_to_string(
            template_name, context, context_instance=RequestContext(request)
            )

    def _show_thanks_page(self, request, instance, **kwargs):
        """
        Renders the thanks page after successful form submission.

        :param django.http.HttpRequest request:
        :return str:
        """
        template_name = instance.success_page_template_name or None

        theme = get_theme(request=request, as_instance=True)

        context = {
            'form_entry': instance.form_entry,
            'fobi_theme': theme,
            'fobi_hide_success_page_title': instance.hide_success_page_title,
            'fobi_success_page_title': instance.success_page_title,
            'fobi_success_page_text': instance.success_page_text,
        }

        if not template_name:
            template_name = theme.embed_form_entry_submitted_ajax_template

        self.rendered_output = render_to_string(
            template_name, context, context_instance=RequestContext(request)
            )

    def render(self, **kwargs):
        return getattr(self, 'rendered_output', '')

    def finalize(self, request, response):
        # Always disable caches if this content type is used somewhere
        response['Cache-Control'] = 'no-cache, must-revalidate'


@processor_for(FobiFormPage)
def process_fobi_form(request, page):
    """
    Process the ``FobiFormPage``.
    """
    fobi_form_processor = FobiFormProcessor()
    response = fobi_form_processor.process(
        request, instance=page.get_content_model()
        )

    if response:
        return response

    return {'fobi_form_response': fobi_form_processor.render()}