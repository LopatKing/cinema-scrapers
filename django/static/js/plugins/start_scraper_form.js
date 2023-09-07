function waitAvailableStatus(cinema_id, name, date) {
  $.ajax({
      url: '/get_scraper_status',
      data: {
        cinema_id: cinema_id,
        date: date,
      },
      method: 'POST',
    })
    .done((res) => {
      if (res.status === 'AVAILABLE') {
        addLinkToCSV(cinema_id, name, res.task_id)
        return true
      }
      setTimeout(function() {
        waitAvailableStatus(cinema_id, name, date);
      }, 1000);
    })
    .fail((err) => {
      console.log(err);
    });
}

function addLinkToCSV(cinema_id, name, task_id) {
  $("li[name="+ cinema_id + "]").empty()
  const check_icon = ' <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" ' +
    'class="bi bi-check" viewBox="0 0 16 16"><path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 ' +
    '1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l2.094 2.093 3.473-4.425a.267.267 0 0 1 .02-.022z"/></svg>'
  $("li[name="+ cinema_id + "]").prepend("<a href='/get_csv/" + task_id + "' target='_blank'>" + check_icon + name + "</a>")
}

function addImgToInputLabel() {
  let logos = $(".logo")
  logos.each(function () {
    let cinema_provider_val = $(this).attr("value")

    let img = $("img[value='" + cinema_provider_val + "']")
    if (img === null) return;
    let img_src = img.attr("src")

    let cinema_provider_input = $("input[value='" + cinema_provider_val + "']")
    cinema_provider_input.addClass("d-none")
    let cinema_provider_label = cinema_provider_input.next()
    cinema_provider_label.addClass("text-center")
    let cinema_provider_name = cinema_provider_label.text()
    let img_html = "<img class='logo mb-3' src='" + img_src + "'>"
    cinema_provider_label.empty().append(img_html).append(cinema_provider_name)

  })
}

$(document).ready(() => {
  addImgToInputLabel()
  $(document).on('click', '#start-scan-btn', function() {
    $("#results").empty()
    let selected_cinemas = $('input[name="cinema"]:checked')
    let date_day = $('#id_date_day option:selected').val()
    let date_month = $('#id_date_month option:selected').val()
    let date_year = $('#id_date_year option:selected').val()
    let date_str = date_year + "-" + date_month + "-" + date_day

    selected_cinemas.each(function() {
      let value = $(this).val()
      let id = $(this).attr("id")
      let name = $("label[for='"+ id +"']").text().trim()

      const html = "<li name='"+ value +"' class='mt-1'><div class='spinner-border spinner-border-sm' role='status'>" +
        "<span class='visually-hidden'></span></div> " + name + "</li>"
      $("#results").prepend(html)
      waitAvailableStatus(value, name, date_str)
    });
  });
});