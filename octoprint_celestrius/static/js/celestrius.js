/*
 * View model for OctoPrint-Celestrius
 *
 * Author: Celestrius
 * License: AGPLv3
 */
$(function () {
    function CelestriusViewModel(parameters) {
        var self = this;

        // assign the injected parameters, e.g.:
        self.settingsViewModel = parameters[0];
        self.wizardViewModel = parameters[1];

        // TODO: Implement your plugin's view model here.
    }

    /* view model class, parameters for constructor, container to bind to
     * Please see http://docs.octoprint.org/en/master/plugins/viewmodels.html#registering-custom-viewmodels for more details
     * and a full list of the available options.
     */
    OCTOPRINT_VIEWMODELS.push({
        construct: CelestriusViewModel,
        // ViewModels your plugin depends on, e.g. loginStateViewModel, settingsViewModel, ...
        dependencies: ["settingsViewModel", "wizardViewModel"],
        // Elements to bind to, e.g. #settings_plugin_celestrius, #tab_plugin_celestrius, ...
        elements: ["#settings_plugin_celestrius"],
    });
});
