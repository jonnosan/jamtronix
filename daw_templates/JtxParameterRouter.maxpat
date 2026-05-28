{
	"patcher" : 	{
		"fileversion" : 1,
		"appversion" : 		{
			"major" : 8,
			"minor" : 6,
			"revision" : 0,
			"architecture" : "x64",
			"modernui" : 1
		},
		"classnamespace" : "box",
		"rect" : [ 100.0, 100.0, 720.0, 480.0 ],
		"bglocked" : 0,
		"openinpresentation" : 1,
		"default_fontsize" : 12.0,
		"default_fontface" : 0,
		"default_fontname" : "Arial",
		"gridonopen" : 1,
		"gridsize" : [ 15.0, 15.0 ],
		"gridsnaponopen" : 1,
		"objectsnaponopen" : 1,
		"statusbarvisible" : 2,
		"toolbarvisible" : 1,
		"lefttoolbarpinned" : 0,
		"toptoolbarpinned" : 0,
		"righttoolbarpinned" : 0,
		"bottomtoolbarpinned" : 0,
		"toolbars_unpinned_last_save" : 0,
		"tallnewobj" : 0,
		"boxanimatetime" : 200,
		"enablehscroll" : 1,
		"enablevscroll" : 1,
		"devicewidth" : 0.0,
		"description" : "JTX Parameter Router — receives /jtx/<voice>/<function> OSC and drives 8 Live-mappable parameters.",
		"digest" : "",
		"tags" : "",
		"style" : "",
		"subpatcher_template" : "",
		"assistshowspatchername" : 0,
		"boxes" : [
			{
				"box" : 				{
					"id" : "obj-udp",
					"maxclass" : "newobj",
					"numinlets" : 0,
					"numoutlets" : 2,
					"outlettype" : [ "", "" ],
					"patching_rect" : [ 30.0, 30.0, 110.0, 22.0 ],
					"text" : "udpreceive 11000"
				}
			},
			{
				"box" : 				{
					"id" : "obj-routejtx",
					"maxclass" : "newobj",
					"numinlets" : 1,
					"numoutlets" : 2,
					"outlettype" : [ "", "" ],
					"patching_rect" : [ 30.0, 65.0, 100.0, 22.0 ],
					"text" : "route /jtx"
				}
			},
			{
				"box" : 				{
					"id" : "obj-routevoice",
					"maxclass" : "newobj",
					"numinlets" : 2,
					"numoutlets" : 2,
					"outlettype" : [ "", "" ],
					"patching_rect" : [ 30.0, 100.0, 80.0, 22.0 ],
					"text" : "route"
				}
			},
			{
				"box" : 				{
					"id" : "obj-routefn",
					"maxclass" : "newobj",
					"numinlets" : 1,
					"numoutlets" : 9,
					"outlettype" : [ "", "", "", "", "", "", "", "", "" ],
					"patching_rect" : [ 30.0, 135.0, 460.0, 22.0 ],
					"text" : "route /cutoff /resonance /glide /bend /spare1 /spare2 /spare3 /spare4"
				}
			},
			{
				"box" : 				{
					"id" : "obj-voicename",
					"maxclass" : "live.text",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 180.0, 30.0, 120.0, 22.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 10.0, 10.0, 140.0, 22.0 ],
					"saved_attribute_attributes" : 					{
						"valueof" : 						{
							"parameter_initial" : [ "lead" ],
							"parameter_initial_enable" : 1,
							"parameter_invisible" : 0,
							"parameter_longname" : "voice_name",
							"parameter_modmode" : 0,
							"parameter_shortname" : "voice",
							"parameter_type" : 3
						}
					},
					"text" : "lead",
					"varname" : "voice_name"
				}
			},
			{
				"box" : 				{
					"id" : "obj-sprintfset",
					"maxclass" : "newobj",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"patching_rect" : [ 180.0, 65.0, 110.0, 22.0 ],
					"text" : "sprintf set /%s"
				}
			},
			{
				"box" : 				{
					"id" : "obj-status",
					"maxclass" : "comment",
					"numinlets" : 1,
					"numoutlets" : 0,
					"patching_rect" : [ 320.0, 65.0, 220.0, 22.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 10.0, 40.0, 380.0, 20.0 ],
					"text" : "JTX Parameter Router · /jtx/<voice>/<fn>",
					"varname" : "status_label"
				}
			},
			{
				"box" : 				{
					"id" : "obj-cutoff",
					"maxclass" : "live.dial",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 30.0, 200.0, 50.0, 50.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 10.0, 80.0, 50.0, 50.0 ],
					"saved_attribute_attributes" : 					{
						"valueof" : 						{
							"parameter_initial" : [ 0.5 ],
							"parameter_initial_enable" : 1,
							"parameter_longname" : "Cutoff",
							"parameter_mmax" : 1.0,
							"parameter_mmin" : 0.0,
							"parameter_shortname" : "Cutoff",
							"parameter_type" : 0
						}
					},
					"varname" : "cutoff"
				}
			},
			{
				"box" : 				{
					"id" : "obj-resonance",
					"maxclass" : "live.dial",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 90.0, 200.0, 50.0, 50.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 70.0, 80.0, 50.0, 50.0 ],
					"saved_attribute_attributes" : 					{
						"valueof" : 						{
							"parameter_initial" : [ 0.5 ],
							"parameter_initial_enable" : 1,
							"parameter_longname" : "Resonance",
							"parameter_mmax" : 1.0,
							"parameter_mmin" : 0.0,
							"parameter_shortname" : "Reso",
							"parameter_type" : 0
						}
					},
					"varname" : "resonance"
				}
			},
			{
				"box" : 				{
					"id" : "obj-glide",
					"maxclass" : "live.dial",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 150.0, 200.0, 50.0, 50.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 130.0, 80.0, 50.0, 50.0 ],
					"saved_attribute_attributes" : 					{
						"valueof" : 						{
							"parameter_initial" : [ 0.0 ],
							"parameter_initial_enable" : 1,
							"parameter_longname" : "Glide",
							"parameter_mmax" : 1.0,
							"parameter_mmin" : 0.0,
							"parameter_shortname" : "Glide",
							"parameter_type" : 0
						}
					},
					"varname" : "glide"
				}
			},
			{
				"box" : 				{
					"id" : "obj-bend",
					"maxclass" : "live.dial",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 210.0, 200.0, 50.0, 50.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 190.0, 80.0, 50.0, 50.0 ],
					"saved_attribute_attributes" : 					{
						"valueof" : 						{
							"parameter_initial" : [ 0.0 ],
							"parameter_initial_enable" : 1,
							"parameter_longname" : "Bend",
							"parameter_mmax" : 1.0,
							"parameter_mmin" : -1.0,
							"parameter_shortname" : "Bend",
							"parameter_type" : 0
						}
					},
					"varname" : "bend"
				}
			},
			{
				"box" : 				{
					"id" : "obj-spare1",
					"maxclass" : "live.dial",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 30.0, 270.0, 50.0, 50.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 10.0, 140.0, 50.0, 50.0 ],
					"saved_attribute_attributes" : 					{
						"valueof" : 						{
							"parameter_initial" : [ 0.0 ],
							"parameter_initial_enable" : 1,
							"parameter_longname" : "Spare 1",
							"parameter_mmax" : 1.0,
							"parameter_mmin" : 0.0,
							"parameter_shortname" : "Sp 1",
							"parameter_type" : 0
						}
					},
					"varname" : "spare1"
				}
			},
			{
				"box" : 				{
					"id" : "obj-spare2",
					"maxclass" : "live.dial",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 90.0, 270.0, 50.0, 50.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 70.0, 140.0, 50.0, 50.0 ],
					"saved_attribute_attributes" : 					{
						"valueof" : 						{
							"parameter_initial" : [ 0.0 ],
							"parameter_initial_enable" : 1,
							"parameter_longname" : "Spare 2",
							"parameter_mmax" : 1.0,
							"parameter_mmin" : 0.0,
							"parameter_shortname" : "Sp 2",
							"parameter_type" : 0
						}
					},
					"varname" : "spare2"
				}
			},
			{
				"box" : 				{
					"id" : "obj-spare3",
					"maxclass" : "live.dial",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 150.0, 270.0, 50.0, 50.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 130.0, 140.0, 50.0, 50.0 ],
					"saved_attribute_attributes" : 					{
						"valueof" : 						{
							"parameter_initial" : [ 0.0 ],
							"parameter_initial_enable" : 1,
							"parameter_longname" : "Spare 3",
							"parameter_mmax" : 1.0,
							"parameter_mmin" : 0.0,
							"parameter_shortname" : "Sp 3",
							"parameter_type" : 0
						}
					},
					"varname" : "spare3"
				}
			},
			{
				"box" : 				{
					"id" : "obj-spare4",
					"maxclass" : "live.dial",
					"numinlets" : 1,
					"numoutlets" : 1,
					"outlettype" : [ "" ],
					"parameter_enable" : 1,
					"patching_rect" : [ 210.0, 270.0, 50.0, 50.0 ],
					"presentation" : 1,
					"presentation_rect" : [ 190.0, 140.0, 50.0, 50.0 ],
					"saved_attribute_attributes" : 					{
						"valueof" : 						{
							"parameter_initial" : [ 0.0 ],
							"parameter_initial_enable" : 1,
							"parameter_longname" : "Spare 4",
							"parameter_mmax" : 1.0,
							"parameter_mmin" : 0.0,
							"parameter_shortname" : "Sp 4",
							"parameter_type" : 0
						}
					},
					"varname" : "spare4"
				}
			}
		],
		"lines" : [
			{
				"patchline" : 				{
					"destination" : [ "obj-routejtx", 0 ],
					"source" : [ "obj-udp", 0 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-routevoice", 0 ],
					"source" : [ "obj-routejtx", 0 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-routefn", 0 ],
					"source" : [ "obj-routevoice", 0 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-sprintfset", 0 ],
					"source" : [ "obj-voicename", 0 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-routevoice", 1 ],
					"source" : [ "obj-sprintfset", 0 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-cutoff", 0 ],
					"source" : [ "obj-routefn", 0 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-resonance", 0 ],
					"source" : [ "obj-routefn", 1 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-glide", 0 ],
					"source" : [ "obj-routefn", 2 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-bend", 0 ],
					"source" : [ "obj-routefn", 3 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-spare1", 0 ],
					"source" : [ "obj-routefn", 4 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-spare2", 0 ],
					"source" : [ "obj-routefn", 5 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-spare3", 0 ],
					"source" : [ "obj-routefn", 6 ]
				}
			},
			{
				"patchline" : 				{
					"destination" : [ "obj-spare4", 0 ],
					"source" : [ "obj-routefn", 7 ]
				}
			}
		],
		"styles" : [  ],
		"dependency_cache" : [  ],
		"autosave" : 0
	}
}
