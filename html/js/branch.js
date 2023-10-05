$(document).ready(function() {
    var selectLi = $('<li></li>');
    var select = $('<select></select>');

    var branchOptions = [
        "android-14.0.0_r1",
        "android-13.0.0_r1",
        "android-12.1.0_r1",
        "android-12.0.0_r1",
        "android-11.0.0_r1",
        "android-10.0.0_r1",
        "android-9.0.0_r1",
        "android-8.1.0_r1",
        "android-8.0.0_r1",
        "android-7.1.0_r1",
        "android-7.0.0_r1",
        "android-6.0.0_r1",
        "android-5.1.0_r1",
        "android-5.0.0_r1"
    ];

    var currentBranch = window.location.pathname.match(/android-\d+\.\d+\.\d+_r\d+/);
    currentBranch = currentBranch ? currentBranch[0] : "";

    for (var i = 0; i < branchOptions.length; i++) {
        var option = $('<option></option>').attr('value', branchOptions[i]).text(branchOptions[i]);
        if (branchOptions[i] === currentBranch) {
            option.attr('selected', 'selected');
        }
        select.append(option);
    }

    selectLi.append(select);

    select.on('change', function() {
        var selectedBranch = $(this).val();
        var currentURL = window.location.href;
        var newURL = currentURL.replace(/android-\d+\.\d+\.\d+_r\d+/, selectedBranch);
        window.location.href = newURL;
    });

    $('#bar ul').prepend(selectLi);
});
