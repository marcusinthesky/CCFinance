import edu.stanford.nlp.coref.CorefCoreAnnotations;
import edu.stanford.nlp.coref.data.CorefChain;
import edu.stanford.nlp.ling.CoreAnnotations;
import edu.stanford.nlp.ling.CoreLabel;
import edu.stanford.nlp.pipeline.Annotation;
import edu.stanford.nlp.pipeline.StanfordCoreNLP;
import edu.stanford.nlp.sentiment.SentimentCoreAnnotations;
import edu.stanford.nlp.util.CoreMap;
import java.io.BufferedWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Properties;

/** Run Stanford CoreNLP 4.5.10 locally. Emit offsets and labels only. */
public class Audit {
    static StanfordCoreNLP pipeline(String annotators, Properties p, boolean check) {
        p.setProperty("annotators", annotators);
        return new StanfordCoreNLP(p, check);
    }

    static void sentiment(Path dir) throws Exception {
        var split = pipeline("tokenize,ssplit", new Properties(), true);
        Properties settings = new Properties();
        settings.setProperty("parse.binaryTrees", "true");
        var classify = pipeline("pos,parse,sentiment", settings, false);
        try (var output = Files.newBufferedWriter(dir.resolve("sentiment.tsv"))) {
            for (String line : Files.readAllLines(dir.resolve("spans.tsv"))) {
                String[] fields = line.split("\t");
                int begin = Integer.parseInt(fields[1]), end = Integer.parseInt(fields[2]);
                var doc = new Annotation(Files.readString(dir.resolve("sentiment/" + fields[0] + ".txt")));
                split.annotate(doc);
                String result = "no_containing_sentence";
                for (CoreMap sentence : doc.get(CoreAnnotations.SentencesAnnotation.class)) {
                    if (sentence.get(CoreAnnotations.CharacterOffsetBeginAnnotation.class) > begin ||
                            sentence.get(CoreAnnotations.CharacterOffsetEndAnnotation.class) < end) continue;
                    List<CoreLabel> tokens = sentence.get(CoreAnnotations.TokensAnnotation.class);
                    if (tokens.size() > 200) {
                        result = "over_200_tokens";
                        break;
                    }
                    doc.set(CoreAnnotations.SentencesAnnotation.class, List.of(sentence));
                    doc.set(CoreAnnotations.TokensAnnotation.class, tokens);
                    classify.annotate(doc);
                    result = sentence.get(SentimentCoreAnnotations.SentimentClass.class);
                    break;
                }
                output.write(fields[0] + "\t" + result + "\n");
                output.flush();
            }
        }
    }

    static int codePoints(String text, int offset) {
        return text.codePointCount(0, offset);
    }

    static void coref(Path dir) throws Exception {
        Properties settings = new Properties();
        settings.setProperty("coref.algorithm", "statistical");
        var model = pipeline("tokenize,ssplit,pos,lemma,ner,depparse,coref", settings, true);
        try (BufferedWriter output = Files.newBufferedWriter(dir.resolve("chains.tsv"));
             BufferedWriter done = Files.newBufferedWriter(dir.resolve("coref-completed.txt"));
             var files = Files.list(dir.resolve("coref"))) {
            for (Path path : files.sorted().toList()) {
                String text = Files.readString(path);
                String tag = path.getFileName().toString().replace(".txt", "");
                var doc = new Annotation(text);
                model.annotate(doc);
                List<CoreMap> sentences = doc.get(CoreAnnotations.SentencesAnnotation.class);
                Map<Integer, CorefChain> chains = doc.get(CorefCoreAnnotations.CorefChainAnnotation.class);
                for (var chain : chains.values()) {
                    for (var m : chain.getMentionsInTextualOrder()) {
                        var tokens = sentences.get(m.sentNum-1).get(CoreAnnotations.TokensAnnotation.class);
                        CoreLabel head = tokens.get(m.headIndex-1);
                        output.write(String.join("\t", tag, String.valueOf(chain.getChainID()),
                            m.mentionType.toString(),
                            String.valueOf(codePoints(text, tokens.get(m.startIndex-1).beginPosition())),
                            String.valueOf(codePoints(text, tokens.get(m.endIndex-2).endPosition())),
                            String.valueOf(codePoints(text, head.beginPosition())),
                            String.valueOf(codePoints(text, head.endPosition()))) + "\n");
                    }
                }
                output.flush();
                done.write(tag + "\n");
                done.flush();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args[0].equals("sentiment")) sentiment(Path.of(args[1]));
        else if (args[0].equals("coref")) coref(Path.of(args[1]));
        else throw new IllegalArgumentException("Expected sentiment or coref");
    }
}
