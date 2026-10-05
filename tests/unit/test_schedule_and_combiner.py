"""ScheduleSource file formats and label-driven Combiner (deterministic)."""
import pytest

from PyFlow import Combiner, Item, ItemsQueue, MultiServer, ScheduleSource, SingleLabelStrategy, Sink


@pytest.mark.parametrize("path, expected", [("Data/model_scheduleSource.csv", 4),
                                            ("Data/model_scheduleSource.data", 4),
                                            ("Data/model_scheduleSource.xlsx", 13)])
def test_schedule_source_reads_files(model, path, expected):
    template = Item(0, labels={"PT": 5}, model_item=True)
    source = ScheduleSource("Source", model, file_name=path, model_item=template)
    queue = ItemsQueue(10, "Q", model)
    server = MultiServer(1, "PT", "M", model)
    sink = Sink("Sink", model)
    source.connect([queue])
    queue.connect([server])
    server.connect([sink])
    model.initialize()
    model.run(100)
    n = sink.get_stats_collector().get_var_input_value()
    assert n == source.number_items == expected
    assert model.clock.last_event_time == 5 * n     # all released at t=0, 5 s each


def test_schedule_source_rejects_unknown_format(model):
    with pytest.raises(ValueError, match="Unsupported file type"):
        ScheduleSource("Source", model, file_name="orders.json")


def test_combiner_matches_components_by_label_and_requirement(model):
    """Each plate needs nRefuerzos reinforcements with the same Previa_ID."""
    plates = {"Time": [0, 0, 0], "Name": ["Plate"] * 3, "Q": [1, 1, 1],
              "Previa_ID": ["A", "B", "C"], "nRefuerzos": [1, 2, 1]}
    # Parts come in plate order (the parts queue is FIFO); "Z" matches no plate and stays
    parts = {"Time": [0, 0, 0, 0], "Name": ["Part"] * 4, "Q": [1, 2, 1, 1],
             "Previa_ID": ["A", "B", "C", "Z"]}
    s_plates = ScheduleSource("Plates", model, data_dict=plates)
    s_parts = ScheduleSource("Parts", model, data_dict=parts)
    q_plates = ItemsQueue(100, "Q_plates", model)
    q_parts = ItemsQueue(100, "Q_parts", model)
    welding = Combiner([1], 2, "Welding", model, pull_mode=SingleLabelStrategy("Previa_ID"),
                       update_requirements=True, update_labels=["nRefuerzos"], batch_mode=True)
    sink = Sink("Sink", model)
    s_plates.connect([q_plates])
    s_parts.connect([q_parts])
    q_plates.connect([welding])
    q_parts.connect([welding.get_component_input(0)])
    welding.connect([sink])
    model.initialize()
    model.run(100)
    done = list(sink.get_stats_collector().entry_times)
    assert [p.get_label_value("Previa_ID") for p in done] == ["A", "B", "C"]
    for plate in done:
        subs = plate.get_sub_items()
        assert len(subs) == plate.get_label_value("nRefuerzos")
        assert {s.get_label_value("Previa_ID") for s in subs} == {plate.get_label_value("Previa_ID")}
    assert model.clock.last_event_time == 6
    assert [p.get_label_value("Previa_ID") for p in q_parts.items_q] == ["Z"]


def test_combiner_label_mismatch_blocks_fifo_queue(model):
    """A component at the head of a FIFO queue that the combiner does not want blocks the
    ones behind it (head-of-line blocking, as in SimuLean/FlexSim)."""
    plates = {"Time": [0], "Name": ["Plate"], "Q": [1], "Previa_ID": ["A"]}
    parts = {"Time": [0, 0], "Name": ["Part"] * 2, "Q": [1, 1], "Previa_ID": ["B", "A"]}
    s_plates = ScheduleSource("Plates", model, data_dict=plates)
    s_parts = ScheduleSource("Parts", model, data_dict=parts)
    q_plates = ItemsQueue(10, "Q_plates", model)
    q_parts = ItemsQueue(10, "Q_parts", model)
    welding = Combiner([1], 2, "Welding", model, pull_mode=SingleLabelStrategy("Previa_ID"))
    sink = Sink("Sink", model)
    s_plates.connect([q_plates])
    s_parts.connect([q_parts])
    q_plates.connect([welding])
    q_parts.connect([welding.get_component_input(0)])
    welding.connect([sink])
    model.initialize()
    model.run(100)
    assert sink.get_stats_collector().get_var_input_value() == 0
    assert [p.get_label_value("Previa_ID") for p in q_parts.items_q] == ["B", "A"]
