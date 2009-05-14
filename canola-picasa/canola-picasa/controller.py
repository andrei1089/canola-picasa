import evas
import ecore
import locale
import logging

from terra.core.manager import Manager
from terra.ui.base import PluginThemeMixin
from terra.core.controller import Controller
from terra.core.threaded_func import ThreadedFunction

manager = Manager()
GeneralActionButton = manager.get_class("Widget/ActionButton")
BaseListController = manager.get_class("Controller/Folder")
BaseRowRenderer =  manager.get_class("Widget/RowRenderer")
ResizableRowRenderer = manager.get_class("Widget/ResizableRowRenderer")
OptionsControllerMixin = manager.get_class("OptionsControllerMixin")
WaitNotifyModel = manager.get_class("Model/WaitNotify")
NotifyModel = manager.get_class("Model/Notify")


log = logging.getLogger("plugins.canola-picasa.controller")


class ActionButton(PluginThemeMixin, GeneralActionButton):
    plugin = "picasa"


class GeneralRowRenderer(PluginThemeMixin, BaseRowRenderer):
    """
    This renderer is applied on ServiceController. Providing
    a personalized list item for albums. It shows the following album 
    properties: title, thumb, number of pictures, data it was created.

    @note: This renderer extends BaseRowRenderer, overloading
    some methods.

    @note: An instance of this class can be reused to show properties
    of diferent models due to optimizations. So, to take full advantages
    of this feature, you can load heavy data like images, on value_set method,
    only keeping in the models the path to load the data. This has a nice
    effect with memory usage and is very scalable. For example if you have a
    list with 6 renderers, and your list has 800 images, only 6 images are
    stored in memory, not 800 (generally the number of renderers is close to
    the number of visible items on the list).

    @note: To tell Canola to look first on the plugin theme you have to
    add PluginThemeMixin class and set the plugin variable with the plugin
    name.

    @see: ServiceController, BaseRowRenderer, PluginThemeMixin
    """
    plugin = "picasa"

    def __init__(self, parent, theme=None):
        BaseRowRenderer.__init__(self, parent, theme)
        self.image = self.evas.FilledImage()
        self.part_swallow("contents", self.image)
        self.signal_emit("thumb,hide", "")

        self.bg_selection = self.PluginEdjeWidget("widget/list/bg_selection")
        self.part_swallow("selection", self.bg_selection)

        self.delete_button = ActionButton(self)
        self.delete_button.state_set(ActionButton.STATE_TRASH)
        self.delete_button.on_button_delete_pressed_set(self.cb_delete_pressed)
        self.part_swallow("delete_button", self.delete_button)

        self.delete_button.on_contents_box_expanded_set(self.cb_box_expanded)
        self.delete_button.on_contents_box_collapsed_set(self.cb_box_collapsed)
        self.delete_button.disable_download()

    def theme_changed(self, end_callback=None):
        def cb(*ignored):
            self.part_swallow("selection", self.bg_selection)
            self.part_swallow("delete_button", self.delete_button)
            self.part_swallow("contents", self.image)
            if end_callback is not None:
                end_callback(self)

        self.bg_selection.theme_changed()
        self.delete_button.theme_changed()
        self.delete_button.state_set(ActionButton.STATE_TRASH)
        self.delete_button.disable_download()

        BaseRowRenderer.theme_changed(self, cb)

    def cb_box_expanded(self, *ignored):
        self._model.selected_state = True

    def cb_box_collapsed(self, *ignored):
        self._model.selected_state = False

    def cb_delete_pressed(self, *ignored):
        def cb_collapsed(*ignored):
            self.delete_button.signal_callback_del("contents_box,collapsed", "",
                                                   cb_collapsed)
            self._model.parent.delete_model(self._model.id)
            self._model.parent.children.remove(self._model)
            self.delete_button.signal_emit("unblock,events", "")
            self.delete_button.state_set(ActionButton.STATE_TRASH)

        self.delete_button.signal_callback_add("contents_box,collapsed", "",
                                               cb_collapsed)

    def cb_load_thumbnail(self):
        try:
            self.image.file_set(self._model.thumb_local)
            self.signal_emit("thumb,show", "")
        except Exception, e:
            log.error("could not load image %r: %s", self._model.thumb_local, e)
            self.signal_emit("thumb,hide", "")

    def value_set(self, model):
        """Apply the model properties to the renderer."""
        if not model or model is self._model:
            return

        self._model = model
        self.part_text_set("album_title", model.name)
        self.part_text_set("album_date", "Date:" + model.date)
        self.part_text_set("album_description", model.description)
        self.part_text_set("album_cnt_photos", "Photos: "+ model.cntPhotos )
        #TODO: do not modify thumb's l/h ratio
        model.request_thumbnail(self.cb_load_thumbnail)

    @evas.decorators.del_callback
    def __on_delete(self):
        """Free internal data on delete."""
        self.image.delete()
        #self.rating_area.delete()
        self.bg_selection.delete()
        self.delete_button.delete()


class ResizableRowRendererWidget(GeneralRowRenderer, ResizableRowRenderer):
    """Picasa Base List Item Renderer for Selected Items.

    This renderer is very similar with RowRendererWidget. The diference
    is the select animation that it starts.

    @see: ServiceController, RowRendererWidget
    """
    row_group="list_item_picasa_resizeable"

    def __init__(self, parent, theme=None):
        GeneralRowRenderer.__init__(self, parent, theme)


class RowRendererWidget(GeneralRowRenderer):
    row_group="list_item_picasa"
    resizable_row_renderer = ResizableRowRendererWidget


class ServiceController(BaseListController, OptionsControllerMixin):
    """Picasa Album List.

    This list is like a page result that shows the videos that match
    with some criteria.

    @note: This class extends BaseListController, but apply a different
    item renderer declaring a row_renderer variable and a different
    screen interface declaring a list_group variable. The group "list_video"
    is the interface of the default Canola video list.

    @see: BaseListController, RowRendererWidget,
          SelectedRowRendererWidget
    """
    terra_type = "Controller/Folder/Task/Image/Picasa/Service"
    row_renderer = RowRendererWidget
    list_group = "list_video"

    def __init__(self, model, canvas, parent):
        self.empty_msg = model.empty_msg
        BaseListController.__init__(self, model, canvas, parent)
        OptionsControllerMixin.__init__(self)
        self.model.callback_notify = self._show_notify

    def _show_notify(self, err):
        """Popup a modal with a notify message."""
        self.parent.show_notify(err)

class PicasaController(BaseListController, Controller):
    terra_type = "Controller/Folder/Task/Image/Picasa"

    def __init__(self, model, canvas, parent):
        
        def th_function(self):
            self.model.load() 
        

        def th_finished(exception, retval):
            self.waitDialog.stop()
            #TODO: get Reason
            if not self.model.login_successful:
                dialog = NotifyModel("Failed to connect to picasa", "Failed to connect to Picasa<br>" +\
                        self.model.login_error, answer_callback=None)
                self.parent.show_notify(dialog)

        
        Controller.__init__(self, model, canvas, parent)
        self.animating = False
        
        self.waitDialog = WaitNotifyModel("Connecting to Picasa,<br> please wait...", 1000);
        self.parent.show_notify(self.waitDialog);

        ThreadedFunction(th_finished, th_function, self).start()
        self._setup_view()

        # should be after setup UI
        self.model.changed_callback_add(self._update_ui)
        self.model.callback_state_changed = self._model_state_changed
        self._check_model_loaded()

