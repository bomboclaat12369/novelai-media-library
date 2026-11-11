using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace NovelAI.MediaSuite
{
    internal sealed class Locations : Form
    {
        private readonly TextBox[] fields = new TextBox[4];
        private readonly string[] names = {"Media folder (contains library.json)", "Media Library program", "Workbench program", "After Hours program"};
        internal Locations(Preferences settings)
        {
            Text="Suite locations"; StartPosition=FormStartPosition.CenterParent; MinimizeBox=false; MaximizeBox=false;
            FormBorderStyle=FormBorderStyle.FixedDialog; AutoScaleMode=AutoScaleMode.Dpi; ClientSize=new Size(590,320);
            Font=SystemFonts.MessageBoxFont;
            var grid = new TableLayoutPanel { Dock=DockStyle.Fill, ColumnCount=2, RowCount=9, Padding=new Padding(14) };
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100)); grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            Controls.Add(grid);
            var paths = new[]{settings.LibraryFolder,settings.CompanionFolder,settings.WorkbenchFolder,settings.GameFolder};
            for (int i=0;i<fields.Length;i++)
            {
                var index=i;
                var label=new Label {Text=names[i],AutoSize=true,Anchor=AnchorStyles.Bottom|AnchorStyles.Left};
                grid.Controls.Add(label,0,i*2); grid.SetColumnSpan(label,2);
                var field=fields[i]=new TextBox {Dock=DockStyle.Fill,Text=paths[i]??""};
                var choose=new Button {Text="Browse…",AutoSize=true};
                choose.Click+=(s,e)=> {
                    using (var dialog=new FolderBrowserDialog {Description=names[index],ShowNewFolderButton=false})
                    {
                        if (Directory.Exists(field.Text)) dialog.SelectedPath=field.Text;
                        if (dialog.ShowDialog(this)==DialogResult.OK) field.Text=dialog.SelectedPath;
                    }
                };
                grid.Controls.Add(field,0,i*2+1); grid.Controls.Add(choose,1,i*2+1);
            }
            var actions=new FlowLayoutPanel {Dock=DockStyle.Fill,FlowDirection=FlowDirection.RightToLeft,AutoSize=true};
            var save=new Button {Text="Save locations",AutoSize=true};
            var cancel=new Button {Text="Cancel",DialogResult=DialogResult.Cancel,AutoSize=true};
            save.Click+=(s,e)=> {
                try
                {
                    var resolved=new string[4];
                    for (int i=0;i<4;i++)
                    {
                        var path=Environment.ExpandEnvironmentVariables(fields[i].Text.Trim().Trim('"'));
                        if (path=="") continue;
                        if (i==0) resolved[i]=Installations.InFolder(Installations.LibraryDirectory(path),Installations.Library,"");
                        if (i==1) resolved[i]=Installations.InFolder(path,Installations.Companion,"");
                        if (i==2) resolved[i]=Installations.InFolder(path,Installations.Workbench,"","duplicate-review");
                        if (i==3) resolved[i]=Installations.InFolder(path,Installations.Game,"","game",Path.Combine("project","game"));
                        if (resolved[i]==null) { fields[i].Focus(); throw new IOException("Could not find "+names[i]+" in that location."); }
                    }
                    settings.LibraryFolder=resolved[0];settings.CompanionFolder=resolved[1];settings.WorkbenchFolder=resolved[2];settings.GameFolder=resolved[3];
                    DialogResult=DialogResult.OK;
                }
                catch(Exception err) {MessageBox.Show(this,err.Message,Text);}
            };
            actions.Controls.Add(save);actions.Controls.Add(cancel); grid.Controls.Add(actions,0,8);grid.SetColumnSpan(actions,2);
            AcceptButton=save; CancelButton=cancel;
        }
    }
}
